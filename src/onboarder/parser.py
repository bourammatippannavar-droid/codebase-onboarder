import ast
from pathlib import Path

from onboarder.models import FileFacts, ImportRef, Symbol, SymbolKind


def _is_main_guard(test: ast.expr) -> bool:
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq):
        return False
    left, right = test.left, test.comparators[0]
    return (
        isinstance(left, ast.Name)
        and left.id == "__name__"
        and isinstance(right, ast.Constant)
        and right.value == "__main__"
    ) or (
        isinstance(right, ast.Name)
        and right.id == "__name__"
        and isinstance(left, ast.Constant)
        and left.value == "__main__"
    )


def _qualified_path(path: Path, project_root: Path) -> str:
    try:
        relative = path.relative_to(project_root)
    except ValueError:
        relative = Path(path.name)
    if relative.parts and relative.parts[0] == "src":
        relative = Path(*relative.parts[1:])
    return relative.as_posix()


def parse_python_file(path: Path, project_root: Path | None = None) -> FileFacts:
    """Extract symbols and imports from text without executing the file."""
    path = Path(path).resolve()
    root = Path(project_root).resolve() if project_root is not None else path.parent
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return FileFacts((), (), (f"could not read file: {exc}",), False)

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        location = f"line {exc.lineno}: " if exc.lineno is not None else ""
        return FileFacts((), (), (f"{location}{exc.msg}",), False)

    relative_path = _qualified_path(path, root)
    symbols: list[Symbol] = []

    def visit_body(body: list[ast.stmt], prefix: tuple[str, ...], in_class: bool) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                name_parts = (*prefix, node.name)
                symbols.append(
                    Symbol(
                        "class",
                        node.name,
                        f"{relative_path}::{'.'.join(name_parts)}",
                        path,
                        node.lineno,
                        node.end_lineno or node.lineno,
                    )
                )
                visit_body(node.body, name_parts, True)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind: SymbolKind = "method" if in_class else "function"
                name_parts = (*prefix, node.name)
                symbols.append(
                    Symbol(
                        kind,
                        node.name,
                        f"{relative_path}::{'.'.join(name_parts)}",
                        path,
                        node.lineno,
                        node.end_lineno or node.lineno,
                    )
                )
                visit_body(node.body, name_parts, False)

    visit_body(tree.body, (), False)
    symbols.sort(key=lambda symbol: (symbol.start_line, symbol.qualified_name))

    imports: list[ImportRef] = []
    import_nodes = (
        node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
    )
    for node in sorted(import_nodes, key=lambda item: (item.lineno, item.col_offset)):
        if isinstance(node, ast.Import):
            imports.extend(
                ImportRef(alias.name, (), 0, node.lineno, (alias.asname,))
                for alias in node.names
            )
        else:
            imports.append(
                ImportRef(
                    node.module or "",
                    tuple(alias.name for alias in node.names),
                    node.level,
                    node.lineno,
                    tuple(alias.asname for alias in node.names),
                )
            )

    has_main_guard = any(
        _is_main_guard(node.test)
        for node in ast.walk(tree)
        if isinstance(node, ast.If)
    )
    return FileFacts(tuple(symbols), tuple(imports), (), has_main_guard)