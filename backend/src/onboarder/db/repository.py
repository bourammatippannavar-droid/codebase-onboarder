from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from onboarder.db.models import EdgeModel, FileModel, RepositoryModel, SymbolModel
from onboarder.services.protocols import (
    AnalysisSnapshot,
    EdgeInput,
    EdgeRecord,
    FileInput,
    FileRecord,
    RepositorySummary,
    SymbolInput,
    SymbolRecord,
)


class SqlAlchemyRepository:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def start_analysis(self, name: str, local_path: Path) -> UUID:
        path_text = str(local_path)
        with self._sessions.begin() as session:
            previous = session.scalar(
                select(RepositoryModel).where(RepositoryModel.local_path == path_text)
            )
            if previous is not None:
                session.delete(previous)
                session.flush()
            repository = RepositoryModel(
                name=name,
                local_path=path_text,
                status="running",
                stats={},
            )
            session.add(repository)
            session.flush()
            return repository.id

    def complete_analysis(
        self,
        repository_id: UUID,
        files: tuple[FileInput, ...],
        symbols: tuple[SymbolInput, ...],
        edges: tuple[EdgeInput, ...],
        stats: dict[str, int],
    ) -> None:
        with self._sessions.begin() as session:
            repository = session.get(RepositoryModel, repository_id)
            if repository is None:
                raise LookupError("repository analysis no longer exists")
            file_ids: dict[str, UUID] = {}
            for file_input in files:
                row = FileModel(
                    repository_id=repository_id,
                    path=file_input.path,
                    loc=file_input.loc,
                    is_entry_point=file_input.is_entry_point,
                    parse_status=file_input.parse_status,
                )
                session.add(row)
                session.flush()
                file_ids[file_input.path] = row.id

            symbol_ids: dict[str, UUID] = {}
            for symbol_input in symbols:
                symbol_row = SymbolModel(
                    file_id=file_ids[symbol_input.file_path],
                    kind=symbol_input.kind,
                    name=symbol_input.name,
                    qualified_name=symbol_input.qualified_name,
                    start_line=symbol_input.start_line,
                    end_line=symbol_input.end_line,
                )
                session.add(symbol_row)
                session.flush()
                symbol_ids[symbol_input.qualified_name] = symbol_row.id

            for edge_input in edges:
                session.add(
                    EdgeModel(
                        repository_id=repository_id,
                        kind=edge_input.kind,
                        src_file_id=file_ids[edge_input.src_file],
                        src_symbol_id=symbol_ids.get(edge_input.src_symbol or ""),
                        dst_file_id=file_ids.get(edge_input.dst_file or ""),
                        dst_symbol_id=symbol_ids.get(edge_input.dst_symbol or ""),
                        dst_name=edge_input.dst_name,
                        confidence=edge_input.confidence,
                        origin=edge_input.origin,
                        is_constructor=edge_input.is_constructor,
                        line=edge_input.line,
                    )
                )
            repository.stats = stats
            repository.status = "ready"
            repository.error = None
            repository.finished_at = func.now()
            session.flush()

    def fail_analysis(self, repository_id: UUID, error: str) -> None:
        with self._sessions.begin() as session:
            repository = session.get(RepositoryModel, repository_id)
            if repository is None:
                return
            session.execute(delete(EdgeModel).where(EdgeModel.repository_id == repository_id))
            session.execute(delete(FileModel).where(FileModel.repository_id == repository_id))
            repository.status = "failed"
            repository.error = error[:120]
            repository.stats = {}
            repository.finished_at = func.now()
            session.flush()

    def list_repositories(self) -> tuple[RepositorySummary, ...]:
        with self._sessions() as session:
            rows = session.scalars(
                select(RepositoryModel).order_by(RepositoryModel.created_at, RepositoryModel.id)
            )
            return tuple(_repository_summary(row) for row in rows)

    def get_analysis(self, repository_id: UUID) -> AnalysisSnapshot | None:
        with self._sessions() as session:
            repository = session.get(RepositoryModel, repository_id)
            if repository is None:
                return None
            files = tuple(
                session.scalars(
                    select(FileModel)
                    .where(FileModel.repository_id == repository_id)
                    .order_by(FileModel.path)
                )
            )
            file_paths = {row.id: row.path for row in files}
            symbols = tuple(
                session.scalars(
                    select(SymbolModel)
                    .join(FileModel)
                    .where(FileModel.repository_id == repository_id)
                    .order_by(SymbolModel.qualified_name)
                )
            )
            symbol_names = {row.id: row.qualified_name for row in symbols}
            edges = tuple(
                session.scalars(
                    select(EdgeModel)
                    .where(EdgeModel.repository_id == repository_id)
                    .order_by(EdgeModel.src_file_id, EdgeModel.line, EdgeModel.dst_name)
                )
            )
            return AnalysisSnapshot(
                _repository_summary(repository),
                tuple(
                    FileRecord(
                        row.id, row.repository_id, row.path, row.loc,
                        row.is_entry_point, row.parse_status
                    )
                    for row in files
                ),
                tuple(
                    SymbolRecord(
                        row.id, row.file_id, file_paths[row.file_id], row.kind, row.name,
                        row.qualified_name, row.start_line, row.end_line
                    )
                    for row in symbols
                ),
                tuple(
                    EdgeRecord(
                        row.id,
                        row.repository_id,
                        row.kind,
                        row.src_file_id,
                        file_paths[row.src_file_id],
                        row.src_symbol_id,
                        symbol_names[row.src_symbol_id] if row.src_symbol_id is not None else None,
                        row.dst_file_id,
                        file_paths[row.dst_file_id] if row.dst_file_id is not None else None,
                        row.dst_symbol_id,
                        symbol_names[row.dst_symbol_id] if row.dst_symbol_id is not None else None,
                        row.dst_name,
                        row.confidence,
                        row.origin,
                        row.is_constructor,
                        row.line,
                    )
                    for row in edges
                ),
            )


def _repository_summary(row: RepositoryModel) -> RepositorySummary:
    stats: dict[str, Any] = row.stats
    return RepositorySummary(
        row.id,
        row.name,
        Path(row.local_path),
        row.status,
        row.error,
        {key: int(value) for key, value in stats.items()},
        row.created_at,
        row.finished_at,
    )
