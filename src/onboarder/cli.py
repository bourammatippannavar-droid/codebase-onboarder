from pathlib import Path

import typer

from onboarder.graph import DependencyGraph, build_graph
from onboarder.models import Confidence, Edge
from onboarder.parser import parse_python_file
from onboarder.resolver import resolve_project
from onboarder.scanner import find_python_files

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Scan Python codebases and inspect their import dependencies."""


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _edge_key(edge: Edge, root: Path) -> tuple[str, int, str, str]:
    return (
        _display_path(edge.src_file, root),
        edge.line,
        edge.dst_name,
        str(edge.confidence),
    )


def _print_edge(edge: Edge, root: Path) -> None:
    destination = (
        _display_path(edge.dst_file, root) if edge.dst_file is not None else edge.dst_name
    )
    external_status = (
        f"{edge.confidence}:{edge.origin}"
        if edge.confidence == Confidence.EXTERNAL
        else str(edge.confidence)
    )
    typer.echo(
        f"  [{external_status}] "
        f"{_display_path(edge.src_file, root)}:{edge.line}"
        f" -> {destination} ({edge.dst_name})"
    )


def _project(root: Path) -> tuple[Path, tuple[Path, ...], tuple[Edge, ...], DependencyGraph]:
    root = root.absolute()
    if root.is_symlink() or not root.is_dir():
        raise typer.BadParameter(f"{root} is not a scannable directory")
    files = tuple(find_python_files(root))
    edges = resolve_project(root)
    return root, files, edges, build_graph(root, edges)


def _project_file(root: Path, file: Path, files: tuple[Path, ...]) -> Path:
    candidate = file if file.is_absolute() else root / file
    candidate = candidate.resolve()
    normalized_files = {path.resolve() for path in files}
    if candidate not in normalized_files:
        raise typer.BadParameter(f"{file} is not a scannable Python file under {root}")
    return candidate


@app.command()
def scan(path: Path) -> None:
    """List Python symbols, imports, resolution edges, and cycles under PATH."""
    root, files, edges, graph = _project(path)
    for file in files:
        facts = parse_python_file(file, project_root=root)
        typer.echo(_display_path(file, root))
        if facts.diagnostics:
            for diagnostic in facts.diagnostics:
                typer.echo(f"  Syntax error: {diagnostic}")
            continue
        typer.echo(f"  Classes: {', '.join(facts.classes) or '(none)'}")
        typer.echo(f"  Functions: {', '.join(facts.functions) or '(none)'}")
        typer.echo(f"  Imports: {', '.join(item.render() for item in facts.imports) or '(none)'}")
        typer.echo(f"  Main guard: {'yes' if facts.has_main_guard else 'no'}")
        for symbol in facts.symbols:
            typer.echo(
                f"  Symbol: {symbol.kind} {symbol.qualified_name} "
                f"(lines {symbol.start_line}-{symbol.end_line})"
            )

    typer.echo("Edges:")
    for edge in sorted(edges, key=lambda item: _edge_key(item, root)):
        _print_edge(edge, root)
    _print_cycles(graph, root)


@app.command()
def deps(path: Path, file: Path) -> None:
    """Show import edges for FILE in project PATH."""
    root, files, edges, _ = _project(path)
    source = _project_file(root, file, files)
    selected = sorted(
        (edge for edge in edges if edge.src_file == source),
        key=lambda item: (item.line, item.dst_name, str(item.confidence)),
    )
    typer.echo(f"Dependencies of {_display_path(source, root)}:")
    if not selected:
        typer.echo("  (none)")
    for edge in selected:
        _print_edge(edge, root)


@app.command("used-by")
def used_by(
    path: Path,
    file: Path,
    transitive: bool = typer.Option(False, "--transitive"),
    depth: int = typer.Option(3, "--depth", min=1),
) -> None:
    """Show files that import FILE, optionally following dependents transitively."""
    root, files, edges, graph = _project(path)
    target = _project_file(root, file, files)
    dependents = (
        graph.transitive_dependents(target, depth) if transitive else graph.dependents(target)
    )
    dependent_set = set(dependents)
    selected = sorted(
        (
            edge
            for edge in edges
            if edge.dst_file == target
            or (transitive and edge.dst_file in dependent_set and edge.src_file in dependent_set)
        ),
        key=lambda item: _edge_key(item, root),
    )
    typer.echo(f"Used by {_display_path(target, root)}:")
    if not dependents:
        typer.echo("  (none)")
    else:
        for edge in selected:
            _print_edge(edge, root)
        for dependent in dependents:
            typer.echo(f"  Dependent: {_display_path(dependent, root)}")


@app.command()
def cycles(path: Path) -> None:
    """List circular import groups in project PATH."""
    root, _, _, graph = _project(path)
    _print_cycles(graph, root)


def _print_cycles(graph: DependencyGraph, root: Path) -> None:
    found = graph.find_cycles()
    typer.echo("Cycles:")
    if not found:
        typer.echo("  (none)")
        return
    for cycle in found:
        typer.echo("  " + " -> ".join(_display_path(file, root) for file in cycle))