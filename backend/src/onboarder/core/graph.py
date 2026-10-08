from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from onboarder.core.calls import resolve_calls
from onboarder.core.models import Confidence, Edge, EdgeKind, Symbol
from onboarder.core.parser import parse_python_file
from onboarder.core.resolver import resolve_project
from onboarder.core.scanner import find_python_files


@dataclass(frozen=True)
class DependencyGraph:
    edges: tuple[Edge, ...]
    symbols: tuple[Symbol, ...] = ()
    root: Path | None = None

    def _adjacency(self) -> dict[Path, set[Path]]:
        adjacency: dict[Path, set[Path]] = {}
        for edge in self.edges:
            if (
                edge.kind == EdgeKind.IMPORTS
                and edge.confidence == Confidence.EXACT
                and edge.dst_file is not None
            ):
                adjacency.setdefault(edge.src_file, set()).add(edge.dst_file)
                adjacency.setdefault(edge.dst_file, set())
        return adjacency

    def dependencies(self, file: Path) -> tuple[Path, ...]:
        return tuple(sorted(self._adjacency().get(Path(file), set()), key=_path_key))

    def dependents(self, file: Path) -> tuple[Path, ...]:
        target = Path(file)
        return tuple(
            sorted(
                (source for source, destinations in self._adjacency().items() if target in destinations),
                key=_path_key,
            )
        )

    def transitive_dependents(self, file: Path, max_depth: int) -> tuple[Path, ...]:
        if max_depth < 1:
            return ()
        visited = {Path(file)}
        found: set[Path] = set()
        frontier = {Path(file)}
        for _ in range(max_depth):
            next_frontier = {
                source
                for source, destinations in self._adjacency().items()
                if destinations & frontier and source not in visited
            }
            if not next_frontier:
                break
            found.update(next_frontier)
            visited.update(next_frontier)
            frontier = next_frontier
        return tuple(sorted(found, key=_path_key))

    def callers(self, symbol: str) -> tuple[Edge, ...]:
        qualified_names = self._matching_symbol_names(symbol)
        return self._call_edges(
            lambda edge: edge.dst_symbol in qualified_names
        )

    def callees(self, symbol: str) -> tuple[Edge, ...]:
        qualified_names = self._matching_symbol_names(symbol)
        return self._call_edges(
            lambda edge: edge.src_symbol in qualified_names
        )

    def usages(self, symbol: str) -> tuple[Edge, ...]:
        matching = [item for item in self.symbols if item.qualified_name == symbol]
        if not matching:
            matching = [item for item in self.symbols if item.name == symbol]
        qualified_names = {item.qualified_name for item in matching}
        usages = [
            edge
            for edge in self.edges
            if edge.kind == EdgeKind.CALLS and edge.dst_symbol in qualified_names
        ]
        for target in matching:
            usages.extend(
                edge
                for edge in self.edges
                if edge.kind == EdgeKind.IMPORTS
                and edge.dst_file == target.file
                and edge.dst_name.rsplit(".", maxsplit=1)[-1] == target.name
            )
        return tuple(sorted(set(usages), key=self._edge_key))

    def _matching_symbol_names(self, query: str) -> set[str]:
        if any(symbol.qualified_name == query for symbol in self.symbols):
            return {query}
        return {symbol.qualified_name for symbol in self.symbols if symbol.name == query}

    def _call_edges(self, predicate: Callable[[Edge], bool]) -> tuple[Edge, ...]:
        return tuple(
            sorted(
                (
                    edge
                    for edge in self.edges
                    if edge.kind == EdgeKind.CALLS and predicate(edge)
                ),
                key=self._edge_key,
            )
        )

    def _edge_key(self, edge: Edge) -> tuple[str, int, str, str]:
        root = self.root
        source = edge.src_file.relative_to(root).as_posix() if root else edge.src_file.as_posix()
        return (source, edge.line, edge.dst_name, str(edge.confidence))

    def find_cycles(self) -> tuple[tuple[Path, ...], ...]:
        adjacency = self._adjacency()
        index = 0
        indices: dict[Path, int] = {}
        lowlinks: dict[Path, int] = {}
        stack: list[Path] = []
        on_stack: set[Path] = set()
        cycles: list[tuple[Path, ...]] = []

        def connect(node: Path) -> None:
            nonlocal index
            indices[node] = index
            lowlinks[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)

            for neighbor in sorted(adjacency.get(node, set()), key=_path_key):
                if neighbor not in indices:
                    connect(neighbor)
                    lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
                elif neighbor in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[neighbor])

            if lowlinks[node] == indices[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.remove(member)
                    component.append(member)
                    if member == node:
                        break
                component.sort(key=_path_key)
                if len(component) > 1 or node in adjacency.get(node, set()):
                    cycles.append(tuple(component))

        for node in sorted(adjacency, key=_path_key):
            if node not in indices:
                connect(node)
        return tuple(sorted(cycles, key=lambda cycle: tuple(map(_path_key, cycle))))


def _path_key(path: Path) -> str:
    return path.as_posix()


def build_graph(root: Path, edges: tuple[Edge, ...] | None = None) -> DependencyGraph:
    root = Path(root).absolute()
    import_edges = resolve_project(root) if edges is None else edges
    call_resolution = resolve_calls(root)
    symbols = tuple(
        symbol
        for file in find_python_files(root)
        for symbol in parse_python_file(file, project_root=root).symbols
    )
    all_edges = tuple(
        sorted(
            (*import_edges, *call_resolution.edges),
            key=lambda edge: (
                edge.src_file.relative_to(root).as_posix(),
                edge.line,
                edge.dst_name,
                str(edge.confidence),
            ),
        )
    )
    return DependencyGraph(all_edges, symbols, root)