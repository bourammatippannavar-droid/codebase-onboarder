from dataclasses import dataclass
from pathlib import Path

from onboarder.models import Confidence, Edge
from onboarder.resolver import resolve_project


@dataclass(frozen=True)
class DependencyGraph:
    edges: tuple[Edge, ...]

    def _adjacency(self) -> dict[Path, set[Path]]:
        adjacency: dict[Path, set[Path]] = {}
        for edge in self.edges:
            if edge.confidence == Confidence.EXACT and edge.dst_file is not None:
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
    return DependencyGraph(edges if edges is not None else resolve_project(root))