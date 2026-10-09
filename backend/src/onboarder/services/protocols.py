from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class FileInput:
    path: str
    loc: int
    is_entry_point: bool
    parse_status: str


@dataclass(frozen=True)
class SymbolInput:
    file_path: str
    kind: str
    name: str
    qualified_name: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class EdgeInput:
    kind: str
    src_file: str
    src_symbol: str | None
    dst_file: str | None
    dst_symbol: str | None
    dst_name: str | None
    confidence: str
    origin: str | None
    is_constructor: bool
    line: int


@dataclass(frozen=True)
class RepositorySummary:
    id: UUID
    name: str
    local_path: Path
    status: str
    error: str | None
    stats: dict[str, int]
    created_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True)
class FileRecord:
    id: UUID
    repository_id: UUID
    path: str
    loc: int
    is_entry_point: bool
    parse_status: str


@dataclass(frozen=True)
class SymbolRecord:
    id: UUID
    file_id: UUID
    file_path: str
    kind: str
    name: str
    qualified_name: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class EdgeRecord:
    id: UUID
    repository_id: UUID
    kind: str
    src_file_id: UUID
    src_file_path: str
    src_symbol_id: UUID | None
    src_symbol_name: str | None
    dst_file_id: UUID | None
    dst_file_path: str | None
    dst_symbol_id: UUID | None
    dst_symbol_name: str | None
    dst_name: str | None
    confidence: str
    origin: str | None
    is_constructor: bool
    line: int


@dataclass(frozen=True)
class AnalysisSnapshot:
    repository: RepositorySummary
    files: tuple[FileRecord, ...]
    symbols: tuple[SymbolRecord, ...]
    edges: tuple[EdgeRecord, ...]


class AnalysisRepository(Protocol):
    def start_analysis(self, name: str, local_path: Path) -> UUID: ...

    def complete_analysis(
        self,
        repository_id: UUID,
        files: tuple[FileInput, ...],
        symbols: tuple[SymbolInput, ...],
        edges: tuple[EdgeInput, ...],
        stats: dict[str, int],
    ) -> None: ...

    def fail_analysis(self, repository_id: UUID, error: str) -> None: ...


class QueryRepository(Protocol):
    def list_repositories(self) -> tuple[RepositorySummary, ...]: ...

    def get_analysis(self, repository_id: UUID) -> AnalysisSnapshot | None: ...
