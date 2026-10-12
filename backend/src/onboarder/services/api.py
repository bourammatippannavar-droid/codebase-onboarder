from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
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
from onboarder.services.analyze import AnalysisPathError, validate_analysis_path
from onboarder.services.protocols import (
    AnalysisSnapshot,
    EdgeRecord,
    FileRecord,
    QueryRepository,
    RepositoryBusyError,
    RepositorySummary,
    SearchRecord,
    SymbolRecord,
)
from onboarder.services.queries import GuideResult, guide
from onboarder.settings import Settings


class ServiceError(Exception):
    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Page[T]:
    items: tuple[T, ...]
    total: int


@dataclass(frozen=True)
class RepositoryView:
    id: UUID
    name: str
    path: str
    status: str
    error: str | None
    stats: dict[str, int]
    created_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True)
class FileView:
    id: UUID
    path: str
    loc: int
    is_entry_point: bool
    parse_status: str
    symbols: tuple["SymbolView", ...] = ()


@dataclass(frozen=True)
class SymbolView:
    id: UUID
    file_id: UUID
    file_path: str
    kind: str
    name: str
    qualified_name: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class EdgeView:
    id: UUID
    kind: str
    src_file_id: UUID
    src_file: str
    src_symbol_id: UUID | None
    src_symbol: str | None
    dst_file_id: UUID | None
    dst_file: str | None
    dst_symbol_id: UUID | None
    dst_symbol: str | None
    dst_name: str | None
    confidence: str
    origin: str | None
    is_constructor: bool
    line: int


@dataclass(frozen=True)
class SearchView:
    kind: str
    file_id: UUID
    path: str
    name: str
    qualified_name: str | None
    symbol_id: UUID | None


@dataclass(frozen=True)
class GraphNodeView:
    id: UUID
    path: str


@dataclass(frozen=True)
class GraphView:
    nodes: tuple[GraphNodeView, ...]
    edges: tuple[EdgeView, ...]
    truncated: bool
    total_nodes: int
    total_edges: int


@dataclass(frozen=True)
class ModuleFolderNode:
    id: str
    kind: Literal["folder"]
    name: str
    path: str
    file_count: int
    loc: int
    in_cycle: bool


@dataclass(frozen=True)
class ModuleFileNode:
    id: str
    kind: Literal["file"]
    file_id: UUID
    name: str
    path: str
    loc: int
    imported_by: int
    is_entry_point: bool
    in_cycle: bool
    central: bool


@dataclass(frozen=True)
class ModuleOutsideNode:
    id: str
    kind: Literal["outside"]
    name: str
    path: str
    file_count: int
    loc: int
    in_cycle: bool


@dataclass(frozen=True)
class ModuleGraphEdge:
    source: str
    target: str
    count: int
    in_cycle: bool


@dataclass(frozen=True)
class ModuleGraphView:
    nodes: tuple[ModuleFolderNode | ModuleFileNode | ModuleOutsideNode, ...]
    edges: tuple[ModuleGraphEdge, ...]
    truncated: bool
    total_nodes: int


@dataclass(frozen=True)
class TreeFolder:
    name: str
    path: str
    file_count: int


@dataclass(frozen=True)
class TreeFile:
    file_id: UUID
    name: str
    path: str
    loc: int
    parse_status: str


@dataclass(frozen=True)
class TreeView:
    folders: tuple[TreeFolder, ...]
    files: tuple[TreeFile, ...]


@dataclass(frozen=True)
class OverviewFolder:
    name: str
    loc: int
    files: int


@dataclass(frozen=True)
class OverviewHotspot:
    file_id: UUID
    path: str
    imported_by: int
    blast_radius: int
    loc: int
    flags: tuple[str, ...]


@dataclass(frozen=True)
class ReadingOrderEntry:
    file_id: UUID
    path: str
    reason: str


@dataclass(frozen=True)
class OverviewView:
    files: int
    symbols: int
    loc: int
    cycle_count: int
    folders: tuple[OverviewFolder, ...]
    call_confidence: dict[str, int]
    resolution_rate: float | None
    hotspots: tuple[OverviewHotspot, ...]
    reading_order: tuple[ReadingOrderEntry, ...]


@dataclass(frozen=True)
class SourceView:
    path: str
    language: str
    content: str
    line_count: int


@dataclass(frozen=True)
class NewRepository:
    repository: RepositoryView
    analysis_path: Path


class OnboarderAPI:
    def __init__(self, repository: QueryRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings

    def list_repositories(self) -> tuple[RepositoryView, ...]:
        return tuple(_repository_view(item, self.settings) for item in self.repository.list_repositories())

    def create_repository(self, path: str, name: str) -> NewRepository:
        try:
            analysis_path = validate_analysis_path(Path(path), self.settings.ANALYSIS_ROOT)
            summary = self.repository.create_pending(name, analysis_path)
        except AnalysisPathError as exc:
            raise ServiceError(400, "path_outside_root", "Analysis path is outside the allowed root.") from exc
        except FileNotFoundError as exc:
            raise ServiceError(400, "path_outside_root", "Analysis path is outside the allowed root.") from exc
        except OSError as exc:
            raise ServiceError(400, "path_outside_root", "Analysis path is outside the allowed root.") from exc
        except RepositoryBusyError as exc:
            raise ServiceError(409, "repository_busy", "Repository analysis is already in progress.") from exc
        return NewRepository(_repository_view(summary, self.settings), analysis_path)

    def get_repository(self, repository_id: UUID) -> RepositoryView:
        summary = self.repository.get_repository(repository_id)
        if summary is None:
            raise ServiceError(404, "repository_not_found", "Repository was not found.")
        return _repository_view(summary, self.settings)

    def delete_repository(self, repository_id: UUID) -> None:
        try:
            deleted = self.repository.delete_repository(repository_id)
        except RepositoryBusyError as exc:
            raise ServiceError(409, "repository_busy", "Repository analysis is already in progress.") from exc
        if not deleted:
            raise ServiceError(404, "repository_not_found", "Repository was not found.")

    def files(self, repository_id: UUID, limit: int, offset: int) -> Page[FileView]:
        snapshot = self._ready_snapshot(repository_id)
        items = tuple(_file_view(item) for item in snapshot.files)
        return _page(items, limit, offset)

    def file(self, repository_id: UUID, file_id: UUID) -> FileView:
        snapshot = self._ready_snapshot(repository_id)
        file_row = next((item for item in snapshot.files if item.id == file_id), None)
        if file_row is None:
            raise ServiceError(404, "file_not_found", "File was not found.")
        symbols = tuple(
            _symbol_view(item)
            for item in snapshot.symbols
            if item.file_id == file_id
        )
        return _file_view(file_row, symbols)

    def tree(self, repository_id: UUID, path_prefix: str = "") -> TreeView:
        prefix = _normalize_graph_prefix(path_prefix)
        snapshot = self._ready_snapshot(repository_id)
        normalized_paths = tuple(
            (item, Path(item.path).as_posix().split("/") if item.path else [])
            for item in snapshot.files
        )
        prefix_parts = prefix.split("/") if prefix else []
        folders: dict[str, int] = {}
        files: list[TreeFile] = []

        for item, parts in normalized_paths:
            if parts[: len(prefix_parts)] != prefix_parts:
                continue
            remaining = parts[len(prefix_parts) :]
            if not remaining:
                continue
            if len(remaining) == 1:
                files.append(
                    TreeFile(
                        item.id,
                        remaining[0],
                        item.path,
                        item.loc,
                        item.parse_status,
                    )
                )
            else:
                child_path = "/".join((*prefix_parts, remaining[0]))
                folders[child_path] = folders.get(child_path, 0) + 1

        return TreeView(
            tuple(
                TreeFolder(Path(path).name, path, count)
                for path, count in sorted(folders.items())
            ),
            tuple(sorted(files, key=lambda item: item.path)),
        )

    def source(self, repository_id: UUID, file_id: UUID) -> SourceView:
        snapshot = self._ready_snapshot(repository_id)
        file_row = next(
            (
                item
                for item in snapshot.files
                if item.id == file_id and item.repository_id == repository_id
            ),
            None,
        )
        if file_row is None:
            raise ServiceError(404, "file_not_found", "File was not found.")

        try:
            analysis_root = self.settings.ANALYSIS_ROOT.resolve(strict=True)
            repository_root = snapshot.repository.local_path.resolve(strict=True)
            source_path = (repository_root / file_row.path).resolve(strict=True)
            source_path.relative_to(repository_root)
            source_path.relative_to(analysis_root)
            max_bytes = min(self.settings.MAX_FILE_BYTES, 1_048_576)
            with source_path.open("rb") as source_file:
                content_bytes = source_file.read(max_bytes + 1)
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
            raise ServiceError(404, "file_not_found", "File was not found.") from exc

        if len(content_bytes) > max_bytes:
            raise ServiceError(413, "file_too_large", "Source file exceeds the 1 MB limit.")
        if b"\x00" in content_bytes:
            raise ServiceError(415, "binary_file", "Binary files cannot be displayed.")

        content = content_bytes.decode("utf-8", errors="replace")
        return SourceView(
            file_row.path,
            "python" if Path(file_row.path).suffix.lower() == ".py" else "text",
            content,
            len(content.splitlines()),
        )

    def overview(self, repository_id: UUID) -> OverviewView:
        """Build repository metrics; central files have at least five distinct importers."""
        snapshot = self._ready_snapshot(repository_id)
        graph = _core_graph(snapshot)
        cycle_paths = {
            path.relative_to(snapshot.repository.local_path).as_posix()
            for cycle in graph.find_cycles()
            for path in cycle
        }
        importers: dict[str, set[str]] = {}
        for edge in snapshot.edges:
            if (
                edge.kind == "IMPORTS"
                and edge.confidence == "exact"
                and edge.dst_file_path is not None
            ):
                importers.setdefault(edge.dst_file_path, set()).add(edge.src_file_path)

        folders: dict[str, list[int]] = {}
        for item in snapshot.files:
            parts = Path(item.path).parts
            folder = parts[0] if len(parts) > 1 else "(root)"
            totals = folders.setdefault(folder, [0, 0])
            totals[0] += item.loc
            totals[1] += 1

        calls = {
            confidence: sum(
                edge.kind == "CALLS" and edge.confidence == confidence
                for edge in snapshot.edges
            )
            for confidence in ("exact", "inferred", "unresolved")
        }
        resolved = calls["exact"] + calls["inferred"]
        call_total = resolved + calls["unresolved"]

        ranked = []
        for item in snapshot.files:
            imported_by = len(importers.get(item.path, set()))
            dependents = graph.transitive_dependents(
                snapshot.repository.local_path / item.path, 5
            )
            flags = []
            if item.path in cycle_paths:
                flags.append("cycle")
            if imported_by >= 5:
                flags.append("central")
            ranked.append(
                OverviewHotspot(
                    item.id,
                    item.path,
                    imported_by,
                    len(dependents),
                    item.loc,
                    tuple(flags),
                )
            )
        ranked.sort(key=lambda item: (-item.blast_radius, item.path))

        entry_points = {
            item.path for item in snapshot.files if item.is_entry_point
        }
        file_by_path = {item.path: item for item in snapshot.files}
        ordering = guide(self.repository, repository_id).reading_order
        reading_order = tuple(
            ReadingOrderEntry(
                file_by_path[path].id,
                path,
                "entry point" if path in entry_points else "imported dependency",
            )
            for path in ordering[:8]
            if path in file_by_path
        )
        return OverviewView(
            len(snapshot.files),
            len(snapshot.symbols),
            sum(item.loc for item in snapshot.files),
            len(cycle_paths),
            tuple(
                OverviewFolder(name, totals[0], totals[1])
                for name, totals in sorted(folders.items())
            ),
            calls,
            resolved / call_total if call_total else None,
            tuple(ranked[:10]),
            reading_order,
        )

    def file_relations(
        self,
        repository_id: UUID,
        file_id: UUID,
        dependent: bool,
        transitive: bool,
        depth: int,
        limit: int,
        offset: int,
    ) -> Page[FileView]:
        snapshot = self._ready_snapshot(repository_id)
        selected_file = next((item for item in snapshot.files if item.id == file_id), None)
        if selected_file is None:
            raise ServiceError(404, "file_not_found", "File was not found.")
        graph = _core_graph(snapshot)
        absolute = snapshot.repository.local_path / selected_file.path
        if dependent:
            related = (
                graph.transitive_dependents(absolute, depth)
                if transitive
                else graph.dependents(absolute)
            )
        elif transitive:
            forward = {absolute}
            discovered: set[Path] = set()
            for _ in range(depth):
                next_paths = {
                    dependency
                    for current in forward
                    for dependency in graph.dependencies(current)
                    if dependency not in discovered
                }
                discovered.update(next_paths)
                forward = next_paths
                if not forward:
                    break
            related = tuple(sorted(discovered))
        else:
            related = graph.dependencies(absolute)
        file_by_path = {
            snapshot.repository.local_path / item.path: item for item in snapshot.files
        }
        records = tuple(_file_view(file_by_path[item]) for item in related if item in file_by_path)
        return _page(records, limit, offset)

    def symbol_edges(
        self,
        repository_id: UUID,
        symbol_id: UUID,
        kind: str,
        limit: int,
        offset: int,
        min_confidence: str = "inferred",
    ) -> Page[EdgeView]:
        snapshot = self._ready_snapshot(repository_id)
        symbol = next((item for item in snapshot.symbols if item.id == symbol_id), None)
        if symbol is None:
            raise ServiceError(404, "symbol_not_found", "Symbol was not found.")
        graph = _core_graph(snapshot)
        if kind == "usages":
            selected = graph.usages(symbol.qualified_name)
        elif kind == "callers":
            selected = graph.callers(symbol.qualified_name)
        else:
            selected = graph.callees(symbol.qualified_name)
        rows = _matched_edge_records(snapshot, selected)
        confidence_rank = {"unresolved": 0, "external": 1, "inferred": 2, "exact": 3}
        threshold = confidence_rank[min_confidence]
        filtered = tuple(
            _edge_view(item)
            for item in rows
            if confidence_rank[item.confidence] >= threshold
        )
        return _page(filtered, limit, offset)

    def search(
        self, repository_id: UUID, query: str, limit: int, offset: int
    ) -> Page[SearchView]:
        self._ready_snapshot(repository_id)
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows, total = self.repository.search(repository_id, f"%{escaped}%", limit, offset)
        return Page(tuple(_search_view(item) for item in rows), total)

    def graph(self, repository_id: UUID, max_nodes: int) -> GraphView:
        snapshot = self._ready_snapshot(repository_id)
        visible = tuple(sorted(snapshot.files, key=lambda item: item.path)[:max_nodes])
        visible_ids = {item.id for item in visible}
        edges = tuple(
            _edge_view(item)
            for item in snapshot.edges
            if item.src_file_id in visible_ids
            and (item.dst_file_id is None or item.dst_file_id in visible_ids)
        )
        return GraphView(
            tuple(GraphNodeView(item.id, item.path) for item in visible),
            edges,
            len(visible) < len(snapshot.files) or len(edges) < len(snapshot.edges),
            len(snapshot.files),
            len(snapshot.edges),
        )

    def module_graph(
        self,
        repository_id: UUID,
        path_prefix: str = "",
        include_tests: bool = False,
    ) -> ModuleGraphView:
        """Aggregate one folder level; a nonexistent prefix intentionally returns an empty graph."""
        prefix = _normalize_graph_prefix(path_prefix)
        snapshot = self._ready_snapshot(repository_id)
        files = tuple(
            item
            for item in snapshot.files
            if include_tests or not _is_test_file(item.path)
        )
        prefix_files = tuple(
            item
            for item in files
            if not prefix
            or item.path.startswith(f"{prefix}/")
            or item.path == prefix
        )
        children: dict[str, list[FileRecord]] = {}
        direct_files: list[FileRecord] = []
        prefix_depth = len(Path(prefix).parts) if prefix else 0
        for item in prefix_files:
            parts = Path(item.path).parts
            if len(parts) <= prefix_depth:
                continue
            if len(parts) == prefix_depth + 1:
                direct_files.append(item)
            else:
                folder = "/".join(parts[: prefix_depth + 1])
                children.setdefault(folder, []).append(item)

        cycle_components = _cycle_components(snapshot)
        cycles = set().union(*cycle_components) if cycle_components else set()
        file_paths = {item.path for item in files}
        importers: dict[str, set[str]] = {}
        for edge in snapshot.edges:
            if (
                edge.kind == "IMPORTS"
                and edge.src_file_path in file_paths
                and edge.dst_file_path is not None
                and edge.dst_file_path in file_paths
            ):
                importers.setdefault(edge.dst_file_path, set()).add(edge.src_file_path)

        node_by_file: dict[str, str] = {}
        nodes: list[ModuleFolderNode | ModuleFileNode | ModuleOutsideNode] = []
        for folder_path, members in children.items():
            relative_path = folder_path
            display_name = Path(folder_path).name
            node_id = f"folder:{relative_path}"
            nodes.append(
                ModuleFolderNode(
                    node_id,
                    "folder",
                    display_name,
                    relative_path,
                    len(members),
                    sum(item.loc for item in members),
                    any(item.path in cycles for item in members),
                )
            )
            node_by_file.update((item.path, node_id) for item in members)
        for item in direct_files:
            node_id = f"file:{item.id}"
            nodes.append(
                ModuleFileNode(
                    node_id,
                    "file",
                    item.id,
                    Path(item.path).name,
                    item.path,
                    item.loc,
                    len(importers.get(item.path, set())),
                    item.is_entry_point,
                    item.path in cycles,
                    len(importers.get(item.path, set())) >= 5,
                )
            )
            node_by_file[item.path] = node_id

        file_by_path = {item.path: item for item in files}
        edge_counts: dict[tuple[str, str], tuple[int, bool]] = {}
        outside_members: dict[str, list[FileRecord]] = {}
        for edge in snapshot.edges:
            if edge.kind != "IMPORTS" or edge.dst_file_path is None:
                continue
            source_node = node_by_file.get(edge.src_file_path)
            target_node = node_by_file.get(edge.dst_file_path)
            if source_node is None and target_node is None:
                continue
            if source_node is None:
                source_row = file_by_path.get(edge.src_file_path)
                if source_row is None:
                    continue
                source_node = _outside_node_id(source_row.path)
                outside_members.setdefault(source_node, []).append(source_row)
            if target_node is None:
                target_row = file_by_path.get(edge.dst_file_path)
                if target_row is None:
                    continue
                target_node = _outside_node_id(target_row.path)
                outside_members.setdefault(target_node, []).append(target_row)
            key = (source_node, target_node)
            count, is_cycle = edge_counts.get(key, (0, False))
            edge_counts[key] = (
                count + 1,
                is_cycle
                or any(
                    edge.src_file_path in component
                    and edge.dst_file_path in component
                    for component in cycle_components
                ),
            )

        outside_nodes: dict[str, ModuleOutsideNode] = {}
        for node_id, members in outside_members.items():
            unique_members = {item.path: item for item in members}
            folder_path = node_id.removeprefix("outside:")
            outside_nodes[node_id] = ModuleOutsideNode(
                node_id,
                "outside",
                Path(folder_path).name if folder_path != "(root)" else "(root)",
                folder_path,
                len(unique_members),
                sum(item.loc for item in unique_members.values()),
                any(item.path in cycles for item in unique_members.values()),
            )
        nodes.extend(outside_nodes.values())
        nodes.sort(key=lambda item: (-item.loc, item.path, item.kind))
        total_nodes = len(nodes)
        visible_nodes = nodes[:150]
        visible_ids = {item.id for item in visible_nodes}
        visible_edges = tuple(
            ModuleGraphEdge(source, target, count, is_cycle)
            for (source, target), (count, is_cycle) in sorted(edge_counts.items())
            if source in visible_ids and target in visible_ids
        )
        return ModuleGraphView(
            tuple(visible_nodes),
            visible_edges,
            total_nodes > 150,
            total_nodes,
        )

    def guide(self, repository_id: UUID) -> GuideResult:
        self._ready_snapshot(repository_id)
        return guide(self.repository, repository_id)

    def ready(self) -> None:
        try:
            self.repository.ping()
        except Exception as exc:
            raise ServiceError(503, "database_unavailable", "Database is unavailable.") from exc

    def _ready_snapshot(self, repository_id: UUID) -> AnalysisSnapshot:
        snapshot = self.repository.get_analysis(repository_id)
        if snapshot is None:
            raise ServiceError(404, "repository_not_found", "Repository was not found.")
        if snapshot.repository.status != "ready":
            raise ServiceError(409, "repository_not_ready", "Repository analysis is not ready.")
        return snapshot


def _page[T](items: tuple[T, ...], limit: int, offset: int) -> Page[T]:
    return Page(items[offset : offset + limit], len(items))


def _normalize_graph_prefix(value: str) -> str:
    if "\\" in value or value.startswith("/") or Path(value).is_absolute():
        raise ServiceError(
            422,
            "validation_error",
            "path_prefix must be a relative path using forward slashes.",
        )
    parts = tuple(part for part in value.split("/") if part not in {"", "."})
    if any(part == ".." for part in parts):
        raise ServiceError(
            422,
            "validation_error",
            "path_prefix must not contain parent-directory segments.",
        )
    if parts and ":" in parts[0]:
        raise ServiceError(
            422,
            "validation_error",
            "path_prefix must not be an absolute path.",
        )
    return "/".join(parts)


def _is_test_file(path: str) -> bool:
    parts = tuple(part.casefold() for part in Path(path).parts)
    name = parts[-1]
    return (
        any(part in {"test", "tests", "__tests__"} for part in parts[:-1])
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def _outside_node_id(path: str) -> str:
    parts = Path(path).parts
    top_level = parts[0] if len(parts) > 1 else "(root)"
    return f"outside:{top_level}"


def _cycle_components(snapshot: AnalysisSnapshot) -> tuple[frozenset[str], ...]:
    return tuple(
        frozenset(
            path.relative_to(snapshot.repository.local_path).as_posix()
            for path in cycle
        )
        for cycle in _core_graph(snapshot).find_cycles()
    )


def _repository_view(row: RepositorySummary, settings: Settings) -> RepositoryView:
    try:
        relative_path = row.local_path.resolve().relative_to(settings.ANALYSIS_ROOT.resolve())
    except ValueError as exc:
        raise ServiceError(500, "internal_error", "Repository path is invalid.") from exc
    return RepositoryView(
        row.id,
        row.name,
        relative_path.as_posix() or ".",
        row.status,
        row.error,
        row.stats,
        row.created_at,
        row.finished_at,
    )


def _file_view(
    row: FileRecord, symbols: tuple[SymbolView, ...] = ()
) -> FileView:
    return FileView(
        row.id, row.path, row.loc, row.is_entry_point, row.parse_status, symbols
    )


def _symbol_view(row: SymbolRecord) -> SymbolView:
    return SymbolView(
        row.id, row.file_id, row.file_path, row.kind, row.name, row.qualified_name,
        row.start_line, row.end_line
    )


def _edge_view(row: EdgeRecord) -> EdgeView:
    return EdgeView(
        row.id, row.kind, row.src_file_id, row.src_file_path, row.src_symbol_id,
        row.src_symbol_name, row.dst_file_id, row.dst_file_path, row.dst_symbol_id,
        row.dst_symbol_name, row.dst_name, row.confidence, row.origin,
        row.is_constructor, row.line
    )


def _search_view(row: SearchRecord) -> SearchView:
    return SearchView(
        row.kind, row.file_id, row.path, row.name, row.qualified_name, row.symbol_id
    )


def _core_graph(snapshot: AnalysisSnapshot) -> DependencyGraph:
    root = snapshot.repository.local_path
    symbols = tuple(
        Symbol(
            _symbol_kind(item.kind), item.name, item.qualified_name,
            root / item.file_path, item.start_line, item.end_line
        )
        for item in snapshot.symbols
    )
    edges = tuple(
        Edge(
            EdgeKind(item.kind.lower()), root / item.src_file_path,
            root / item.dst_file_path if item.dst_file_path else None,
            item.dst_name or "", Confidence(item.confidence), item.line,
            _origin(item.origin), item.src_symbol_name, item.dst_symbol_name,
            item.is_constructor
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
    raise ValueError("Stored symbol kind is invalid.")


def _origin(value: str | None) -> ExternalOrigin | None:
    if value == "stdlib":
        return "stdlib"
    if value == "third-party":
        return "third-party"
    if value is None:
        return None
    raise ValueError("Stored edge origin is invalid.")


def _matched_edge_records(
    snapshot: AnalysisSnapshot, selected: tuple[Edge, ...]
) -> tuple[EdgeRecord, ...]:
    keys = {
        (
            edge.kind.value.upper(), edge.src_file, edge.line, edge.dst_name,
            edge.src_symbol, edge.dst_symbol
        )
        for edge in selected
    }
    return tuple(
        item for item in snapshot.edges
        if (
            item.kind, snapshot.repository.local_path / item.src_file_path, item.line,
            item.dst_name or "", item.src_symbol_name, item.dst_symbol_name
        ) in keys
    )
