import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedFile:
    path: Path
    classes: tuple[str, ...]
    functions: tuple[str, ...]
    imports: tuple[str, ...]
    error: str | None = None


def parse_python_file(path: Path) -> ParsedFile:
    """Extract declarations and imports from a Python file without executing it."""
    path = Path(path)
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return ParsedFile(path, (), (), (), f"could not read file: {exc}")

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        location = f"line {exc.lineno}: " if exc.lineno is not None else ""
        return ParsedFile(path, (), (), (), f"{location}{exc.msg}")

    classes = []
    functions = []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.Import):
            imports.extend(
                f"import {alias.name}"
                + (f" as {alias.asname}" if alias.asname else "")
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            names = ", ".join(
                alias.name + (f" as {alias.asname}" if alias.asname else "")
                for alias in node.names
            )
            imports.append(f"from {module} import {names}")

    return ParsedFile(path, tuple(classes), tuple(functions), tuple(imports))