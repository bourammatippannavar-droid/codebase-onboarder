from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ORMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Problem(ORMResponse):
    type: str
    title: str
    status: int
    detail: str
    code: str
    request_id: str


class RepositoryCreate(ORMResponse):
    path: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=255)


class RepositoryResponse(ORMResponse):
    id: UUID
    name: str
    path: str
    status: str
    error: str | None
    stats: dict[str, int]
    created_at: datetime
    finished_at: datetime | None


class SymbolResponse(ORMResponse):
    id: UUID
    file_id: UUID
    file_path: str
    kind: str
    name: str
    qualified_name: str
    start_line: int
    end_line: int


class FileResponse(ORMResponse):
    id: UUID
    path: str
    loc: int
    is_entry_point: bool
    parse_status: str
    symbols: tuple[SymbolResponse, ...] = ()


class EdgeResponse(ORMResponse):
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


class SearchResponseItem(ORMResponse):
    kind: str
    file_id: UUID
    path: str
    name: str
    qualified_name: str | None
    symbol_id: UUID | None


class PageResponse[T](BaseModel):
    items: tuple[T, ...]
    total: int


class GraphNodeResponse(ORMResponse):
    id: UUID
    path: str


class GraphResponse(ORMResponse):
    nodes: tuple[GraphNodeResponse, ...]
    edges: tuple[EdgeResponse, ...]
    truncated: bool
    total_nodes: int
    total_edges: int


class ModuleFolderNodeResponse(ORMResponse):
    id: str
    kind: Literal["folder"]
    name: str
    path: str
    file_count: int
    loc: int
    in_cycle: bool


class ModuleFileNodeResponse(ORMResponse):
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


class ModuleOutsideNodeResponse(ORMResponse):
    id: str
    kind: Literal["outside"]
    name: str
    path: str
    file_count: int
    loc: int
    in_cycle: bool


ModuleGraphNodeResponse = Annotated[
    ModuleFolderNodeResponse | ModuleFileNodeResponse | ModuleOutsideNodeResponse,
    Field(discriminator="kind"),
]


class ModuleGraphEdgeResponse(ORMResponse):
    source: str
    target: str
    count: int
    in_cycle: bool


class ModuleGraphResponse(ORMResponse):
    nodes: tuple[ModuleGraphNodeResponse, ...]
    edges: tuple[ModuleGraphEdgeResponse, ...]
    truncated: bool
    total_nodes: int


class OverviewFolderResponse(ORMResponse):
    name: str
    loc: int
    files: int


class OverviewHotspotResponse(ORMResponse):
    file_id: UUID
    path: str
    imported_by: int
    blast_radius: int
    loc: int
    flags: tuple[str, ...]


class ReadingOrderResponse(ORMResponse):
    file_id: UUID
    path: str
    reason: str


class OverviewResponse(ORMResponse):
    files: int
    symbols: int
    loc: int
    cycle_count: int
    folders: tuple[OverviewFolderResponse, ...]
    call_confidence: dict[str, int]
    resolution_rate: float | None
    hotspots: tuple[OverviewHotspotResponse, ...]
    reading_order: tuple[ReadingOrderResponse, ...]


class SourceResponse(ORMResponse):
    path: str
    language: str
    content: str
    line_count: int


class GuideResponse(ORMResponse):
    entry_points: tuple[str, ...]
    most_imported: tuple[tuple[str, int], ...]
    reading_order: tuple[str, ...]
    cycles: tuple[tuple[str, ...], ...]
    folder_counts: tuple[tuple[str, int], ...]
    call_counts: tuple[tuple[str, int], ...]
    not_stored: tuple[tuple[str, int], ...]
    resolution_rate: float


class HealthResponse(ORMResponse):
    status: str


class ReadyResponse(ORMResponse):
    status: str
