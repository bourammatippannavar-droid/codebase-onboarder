"""Create repository analysis tables.

Revision ID: 20261009_01
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261009_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("local_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column(
            "stats", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'ready', 'failed')",
            name="ck_repositories_status",
        ),
        sa.UniqueConstraint("local_path", name="uq_repositories_local_path"),
    )
    op.create_table(
        "files",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "repository_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("loc", sa.Integer(), nullable=False),
        sa.Column("is_entry_point", sa.Boolean(), nullable=False),
        sa.Column("parse_status", sa.String(16), nullable=False),
        sa.CheckConstraint(
            "parse_status IN ('ok', 'syntax_error', 'skipped')",
            name="ck_files_parse_status",
        ),
        sa.UniqueConstraint("repository_id", "path", name="uq_files_repository_path"),
    )
    op.create_table(
        "symbols",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "file_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("qualified_name", sa.Text(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.CheckConstraint("kind IN ('class', 'function', 'method')", name="ck_symbols_kind"),
        sa.UniqueConstraint("file_id", "qualified_name", name="uq_symbols_file_qualified_name"),
    )
    op.create_table(
        "edges",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "repository_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column(
            "src_file_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "src_symbol_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("symbols.id", ondelete="CASCADE")
        ),
        sa.Column(
            "dst_file_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("files.id", ondelete="CASCADE")
        ),
        sa.Column(
            "dst_symbol_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("symbols.id", ondelete="CASCADE")
        ),
        sa.Column("dst_name", sa.Text()),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("origin", sa.String(32)),
        sa.Column("is_constructor", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("line", sa.Integer(), nullable=False),
        sa.CheckConstraint("kind IN ('IMPORTS', 'CALLS')", name="ck_edges_kind"),
        sa.CheckConstraint(
            "confidence IN ('exact', 'inferred', 'external', 'unresolved')",
            name="ck_edges_confidence",
        ),
    )
    op.create_index("ix_edges_repository_dst_file", "edges", ["repository_id", "dst_file_id"])
    op.create_index("ix_edges_repository_dst_symbol", "edges", ["repository_id", "dst_symbol_id"])
    op.create_index("ix_edges_repository_src_file", "edges", ["repository_id", "src_file_id"])
    op.create_index("ix_symbols_file_id", "symbols", ["file_id"])
    op.create_index("ix_symbols_qualified_name", "symbols", ["qualified_name"])


def downgrade() -> None:
    op.drop_index("ix_symbols_qualified_name", table_name="symbols")
    op.drop_index("ix_symbols_file_id", table_name="symbols")
    op.drop_index("ix_edges_repository_src_file", table_name="edges")
    op.drop_index("ix_edges_repository_dst_symbol", table_name="edges")
    op.drop_index("ix_edges_repository_dst_file", table_name="edges")
    op.drop_table("edges")
    op.drop_table("symbols")
    op.drop_table("files")
    op.drop_table("repositories")
