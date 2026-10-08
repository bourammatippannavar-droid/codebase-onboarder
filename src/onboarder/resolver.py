import ast
import sys
from pathlib import Path

from onboarder.models import Confidence, Edge, EdgeKind, ExternalOrigin, ImportRef
from onboarder.parser import parse_python_file
from onboarder.scanner import find_python_files


def _module_name(path: Path, search_root: Path) -> str:
    relative = path.relative_to(search_root).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _source_roots(root: Path) -> tuple[Path, ...]:
    roots = [root]
    source = root / "src"
    if source.is_dir() and not source.is_symlink():
        roots.insert(0, source)
    return tuple(roots)


def _package_for(module_name: str, path: Path) -> str:
    if path.name == "__init__.py":
        return module_name
    return module_name.rpartition(".")[0]


def _relative_base(module_name: str, path: Path, level: int, module: str) -> str:
    package_parts = _package_for(module_name, path).split(".")
    if package_parts == [""]:
        package_parts = []
    keep = max(0, len(package_parts) - level + 1)
    base_parts = package_parts[:keep]
    if module:
        base_parts.extend(module.split("."))
    return ".".join(part for part in base_parts if part)


def _defined_names(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return set()

    names: set[str] = set()

    def add_target(target: ast.expr) -> None:
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                add_target(element)

    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                add_target(target)
        elif isinstance(node, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


def _resolve_import(
    ref: ImportRef,
    source_file: Path,
    source_module: str,
    module_files: dict[str, Path],
    project_tops: set[str],
) -> list[Edge]:
    relative = ref.level > 0
    base_name = (
        _relative_base(source_module, source_file, ref.level, ref.module)
        if relative
        else ref.module
    )
    if not ref.names:
        return [
            _make_edge(
                source_file,
                base_name,
                module_files.get(base_name),
                relative or base_name.split(".", maxsplit=1)[0] in project_tops,
                ref.line,
            )
        ]

    edges = []
    for name in ref.names:
        imported_name = f"{base_name}.{name}" if base_name else name
        submodule = module_files.get(imported_name)
        if submodule is not None:
            edges.append(_make_edge(source_file, imported_name, submodule, True, ref.line))
            continue

        package_file = module_files.get(base_name)
        if package_file is not None and name in _defined_names(package_file):
            edges.append(_make_edge(source_file, imported_name, package_file, True, ref.line))
            continue

        internal = relative or base_name.split(".", maxsplit=1)[0] in project_tops
        edges.append(_make_edge(source_file, imported_name, None, internal, ref.line))
    return edges


def _make_edge(
    source_file: Path,
    dst_name: str,
    dst_file: Path | None,
    looks_internal: bool,
    line: int,
) -> Edge:
    origin: ExternalOrigin | None = None
    if dst_file is not None:
        confidence = Confidence.EXACT
    elif looks_internal:
        confidence = Confidence.UNRESOLVED
    elif dst_name.split(".", maxsplit=1)[0] in sys.stdlib_module_names:
        confidence = Confidence.EXTERNAL
        origin = "stdlib"
    else:
        confidence = Confidence.EXTERNAL
        origin = "third-party"
    return Edge(EdgeKind.IMPORTS, source_file, dst_file, dst_name, confidence, line, origin)


def resolve_project(root: Path) -> tuple[Edge, ...]:
    """Resolve imports in project files without importing analyzed modules."""
    root = Path(root).absolute()
    if root.is_symlink():
        return ()
    search_roots = _source_roots(root)
    files = sorted(
        {path.resolve() for search_root in search_roots for path in find_python_files(search_root)},
        key=lambda path: path.relative_to(root).as_posix(),
    )

    module_for_file: dict[Path, str] = {}
    module_files: dict[str, Path] = {}
    for path in files:
        search_root = next(base for base in search_roots if path.is_relative_to(base))
        module = _module_name(path, search_root)
        module_for_file[path] = module
        module_files.setdefault(module, path)

    project_tops = {name.split(".", maxsplit=1)[0] for name in module_files}
    edges = []
    for path in files:
        facts = parse_python_file(path, project_root=root)
        if facts.diagnostics:
            continue
        for ref in facts.imports:
            edges.extend(
                _resolve_import(ref, path, module_for_file[path], module_files, project_tops)
            )
    return tuple(
        sorted(
            edges,
            key=lambda edge: (
                edge.src_file.relative_to(root).as_posix(),
                edge.line,
                edge.dst_name,
                str(edge.confidence),
            ),
        )
    )