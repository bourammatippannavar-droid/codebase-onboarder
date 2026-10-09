from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RepositoryModel(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'ready', 'failed')", name="ck_repositories_status"
        ),
        UniqueConstraint("local_path", name="uq_repositories_local_path"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    local_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FileModel(Base):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("repository_id", "path", name="uq_files_repository_path"),
        CheckConstraint(
            "parse_status IN ('ok', 'syntax_error', 'skipped')", name="ck_files_parse_status"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    repository_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    loc: Mapped[int] = mapped_column(Integer, nullable=False)
    is_entry_point: Mapped[bool] = mapped_column(Boolean, nullable=False)
    parse_status: Mapped[str] = mapped_column(String(16), nullable=False)


class SymbolModel(Base):
    __tablename__ = "symbols"
    __table_args__ = (
        UniqueConstraint("file_id", "qualified_name", name="uq_symbols_file_qualified_name"),
        CheckConstraint(
            "kind IN ('class', 'function', 'method')", name="ck_symbols_kind"
        ),
        Index("ix_symbols_file_id", "file_id"),
        Index("ix_symbols_qualified_name", "qualified_name"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    file_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    qualified_name: Mapped[str] = mapped_column(Text, nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)


class EdgeModel(Base):
    __tablename__ = "edges"
    __table_args__ = (
        CheckConstraint("kind IN ('IMPORTS', 'CALLS')", name="ck_edges_kind"),
        CheckConstraint(
            "confidence IN ('exact', 'inferred', 'external', 'unresolved')",
            name="ck_edges_confidence",
        ),
        Index("ix_edges_repository_dst_file", "repository_id", "dst_file_id"),
        Index("ix_edges_repository_dst_symbol", "repository_id", "dst_symbol_id"),
        Index("ix_edges_repository_src_file", "repository_id", "src_file_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    repository_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    src_file_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False
    )
    src_symbol_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("symbols.id", ondelete="CASCADE")
    )
    dst_file_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE")
    )
    dst_symbol_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("symbols.id", ondelete="CASCADE")
    )
    dst_name: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    origin: Mapped[str | None] = mapped_column(String(32))
    is_constructor: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    line: Mapped[int] = mapped_column(Integer, nullable=False)
