from pathlib import Path

import typer

from onboarder.parser import parse_python_file
from onboarder.scanner import find_python_files

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Scan Python codebases."""


@app.command()
def scan(folder: Path) -> None:
    """List classes, functions, and imports in Python files under FOLDER."""
    if not folder.is_dir():
        raise typer.BadParameter(f"{folder} is not a directory")

    for path in find_python_files(folder):
        parsed = parse_python_file(path)
        typer.echo(path.as_posix())
        if parsed.error:
            typer.echo(f"  Syntax error: {parsed.error}")
            continue
        typer.echo(f"  Classes: {', '.join(parsed.classes) or '(none)'}")
        typer.echo(f"  Functions: {', '.join(parsed.functions) or '(none)'}")
        typer.echo(f"  Imports: {', '.join(parsed.imports) or '(none)'}")