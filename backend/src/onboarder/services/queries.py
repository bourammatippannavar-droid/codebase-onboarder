from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from onboarder.core.graph import DependencyGraph
from onboarder.core.models import (
    Confidence,
    Edge,
    EdgeKind,
    ExternalOrigin,
    Symbol,
    SymbolKind,
)
from onboarder.services.protocols import (
    AnalysisSnapshot,
    EdgeRecord,
    FileRecord,
    QueryRepository,
    RepositorySummary,
)


@dataclass(frozen=True)
class GraphNode:
    file: str


@dataclass(frozen=True)
class GraphLink:
    source: str
    destination: str
    kind: str
    line: int


@dataclass(frozen=True)
class GraphResult:
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphLink, ...]
    truncated: bool


@dataclass(frozen=True)
class GuideResult:
    entry_points: tuple[str, ...]
    most_imported: tuple[tuple[str, int], ...]
    reading_order: tuple[str, ...]
    cycles: tuple[tuple[str, ...], ...]
    folder_counts: tuple[tuple[str, int], ...]
    call_counts: tuple[tuple[str, int], ...]
    not_stored: tuple[tuple[str, int], ...]
    resolution_rate: float


def list_repositories(repository: QueryRepository) -> tuple[RepositorySummary, ...]:
    return repository.list_repositories()


def get_files(repository: QueryRepository, repository_id: UUID) -> tuple[FileRecord, ...]:
    snapshot = _snapshot(repository, repository_id)
    return snapshot.files


def dependencies(
    repository: QueryRepository, repository_id: UUID, file_path: str
) -> tuple[FileRecord, ...]:
    snapshot = _snapshot(repository, repository_id)
    graph = _graph(snapshot)
    matching = _file(snapshot, file_path)
    records = {
        snapshot.repository.local_path / record.path: record for record in snapshot.files
    }
    return tuple(
        records[path]
        for path in graph.dependencies(snapshot.repository.local_path / matching.path)
    )


def dependents(
    repository: QueryRepository, repository_id: UUID, file_path: str
) -> tuple[FileRecord, ...]:
    snapshot = _snapshot(repository, repository_id)
    graph = _graph(snapshot)
    matching = _file(snapshot, file_path)
    records = {snapshot.repository.local_path / record.path: record for record in snapshot.files}
    return tuple(records[path] for path in graph.dependents(snapshot.repository.local_path / matching.path))


def usages(
    repository: QueryRepository, repository_id: UUID, symbol: str
) -> tuple[EdgeRecord, ...]:
    snapshot = _snapshot(repository, repository_id)
    _matching_symbols(snapshot, symbol)
    return _matching_edges(snapshot, _graph(snapshot).usages(symbol))


def callers(
    repository: QueryRepository, repository_id: UUID, symbol: str
) -> tuple[EdgeRecord, ...]:
    snapshot = _snapshot(repository, repository_id)
    _matching_symbols(snapshot, symbol)
    selected = _graph(snapshot).callers(symbol)
    return _matching_edges(snapshot, selected)


def callees(
    repository: QueryRepository, repository_id: UUID, symbol: str
) -> tuple[EdgeRecord, ...]:
    snapshot = _snapshot(repository, repository_id)
    _matching_symbols(snapshot, symbol)
    selected = _graph(snapshot).callees(symbol)
    return _matching_edges(snapshot, selected)


def graph(
    repository: QueryRepository, repository_id: UUID, max_nodes: int = 150
) -> GraphResult:
    if max_nodes < 1:
        raise ValueError("max_nodes must be positive")
    snapshot = _snapshot(repository, repository_id)
    visible = tuple(sorted(snapshot.files, key=lambda item: item.path)[:max_nodes])
    visible_paths = {item.path for item in visible}
    selected_edges = tuple(
        item for item in snapshot.edges
        if item.src_file_path in visible_paths
        and (item.dst_file_path is None or item.dst_file_path in visible_paths)
    )
    return GraphResult(
        tuple(GraphNode(item.path) for item in visible),
        tuple(
            GraphLink(
                item.src_file_path,
                item.dst_file_path or item.dst_name or "(unresolved)",
                item.kind,
                item.line,
            )
            for item in selected_edges
        ),
        len(visible) < len(snapshot.files) or len(selected_edges) < len(snapshot.edges),
    )


def guide(repository: QueryRepository, repository_id: UUID) -> GuideResult:
    snapshot = _snapshot(repository, repository_id)
    core_graph = _graph(snapshot)
    root = snapshot.repository.local_path
    entry_points = tuple(sorted(item.path for item in snapshot.files if item.is_entry_point))
    importers: dict[str, set[str]] = {}
    adjacency: dict[str, set[str]] = {}
    for edge in snapshot.edges:
        if edge.kind == "IMPORTS" and edge.confidence == "exact" and edge.dst_file_path:
            importers.setdefault(edge.dst_file_path, set()).add(edge.src_file_path)
            adjacency.setdefault(edge.src_file_path, set()).add(edge.dst_file_path)
    most_imported = tuple(sorted(
        ((path, len(importers[path])) for path in importers),
        key=lambda item: (-item[1], item[0]),
    )[:10])
    reading_order = list(entry_points)
    visited = set(reading_order)
    frontier = set(reading_order)
    for _ in range(2):
        discovered = {
            target for source in frontier for target in adjacency.get(source, set())
            if target not in visited
        }
        ordered = sorted(discovered, key=lambda item: (-len(importers.get(item, set())), item))
        reading_order.extend(ordered)
        visited.update(ordered)
        frontier = set(ordered)
    folder_counts: dict[str, int] = {}
    for item in snapshot.files:
        folder = Path(item.path).parts[0] if len(Path(item.path).parts) > 1 else "(root)"
        folder_counts[folder] = folder_counts.get(folder, 0) + 1
    call_confidences = ("exact", "inferred", "unresolved")
    call_counts = tuple(
        (confidence, sum(
            edge.kind == "CALLS" and edge.confidence == confidence
            for edge in snapshot.edges
        ))
        for confidence in call_confidences
    )
    resolved = dict(call_counts)["exact"] + dict(call_counts)["inferred"]
    unresolved = dict(call_counts)["unresolved"]
    total = resolved + unresolved
    stored = snapshot.repository.stats
    return GuideResult(
        entry_points,
        most_imported,
        tuple(reading_order),
        tuple(
            tuple(path.relative_to(root).as_posix() for path in cycle)
            for cycle in core_graph.find_cycles()
        ),
        tuple(sorted(folder_counts.items())),
        call_counts,
        (
            ("unknown receiver", stored.get("call_unknown_receiver", 0)),
            ("external package", stored.get("call_external_package", 0)),
            ("builtin", stored.get("call_builtin", 0)),
        ),
        resolved / total if total else 0.0,
    )


def _snapshot(repository: QueryRepository, repository_id: UUID) -> AnalysisSnapshot:
    result = repository.get_analysis(repository_id)
    if result is None:
        raise LookupError("repository was not found")
    return result


def _file(snapshot: AnalysisSnapshot, file_path: str) -> FileRecord:
    normalized = Path(file_path).as_posix()
    match = next((item for item in snapshot.files if item.path == normalized), None)
    if match is None:
        raise LookupError("file was not found")
    return match


def _matching_symbols(snapshot: AnalysisSnapshot, symbol: str) -> tuple[Symbol, ...]:
    result = tuple(item for item in snapshot.symbols if item.qualified_name == symbol)
    if not result:
        result = tuple(item for item in snapshot.symbols if item.name == symbol)
    if not result:
        raise LookupError("symbol was not found")
    return tuple(
        Symbol(
            _symbol_kind(item.kind), item.name, item.qualified_name,
            snapshot.repository.local_path / item.file_path,
            item.start_line, item.end_line,
        )
        for item in result
    )


def _graph(snapshot: AnalysisSnapshot) -> DependencyGraph:
    root = snapshot.repository.local_path
    symbols = tuple(
        Symbol(
            _symbol_kind(item.kind), item.name, item.qualified_name, root / item.file_path,
            item.start_line, item.end_line,
        )
        for item in snapshot.symbols
    )
    edges = tuple(
        Edge(
            EdgeKind(item.kind.lower()),
            root / item.src_file_path,
            root / item.dst_file_path if item.dst_file_path else None,
            item.dst_name or "",
            Confidence(item.confidence),
            item.line,
            _origin(item.origin),
            item.src_symbol_name,
            item.dst_symbol_name,
            item.is_constructor,
        )
        for item in snapshot.edges
    )
    return DependencyGraph(edges, symbols, root)


def _symbol_kind(value: str) -> SymbolKind:
    if value == "class":
        return "class"
    if value == "function":
        return "function"
    if value == "method":
        return "method"
    raise ValueError("stored symbol kind is invalid")


def _origin(value: str | None) -> ExternalOrigin | None:
    if value == "stdlib":
        return "stdlib"
    if value == "third-party":
        return "third-party"
    if value is None:
        return None
    raise ValueError("stored edge origin is invalid")


def _matching_edges(
    snapshot: AnalysisSnapshot, selected: tuple[Edge, ...]
) -> tuple[EdgeRecord, ...]:
    wanted = {
        (
            edge.kind.value.upper(), edge.src_file, edge.line, edge.dst_name,
            edge.src_symbol, edge.dst_symbol
        )
        for edge in selected
    }
    return tuple(
        item for item in snapshot.edges
        if (
            item.kind, snapshot.repository.local_path / item.src_file_path,
            item.line, item.dst_name or "", item.src_symbol_name, item.dst_symbol_name
        ) in wanted
    )
