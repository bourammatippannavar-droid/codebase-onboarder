from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from onboarder.db.models import EdgeModel, FileModel, RepositoryModel, SymbolModel
from onboarder.db.repository import SqlAlchemyRepository
from onboarder.services.analyze import AnalyzeRepository
from onboarder.settings import Settings

BACKEND = Path(__file__).parents[1]


@pytest.fixture
def postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[str, sessionmaker[Session]]]:
    database_url = Settings().TEST_DATABASE_URL
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is unset; PostgreSQL integration tests skipped")
    engine = create_engine(database_url)
    try:
        with engine.connect():
            pass
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL is unreachable via TEST_DATABASE_URL: {exc.__class__.__name__}")

    monkeypatch.setenv("ONBOARDER_TEST_MIGRATION", "1")
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    config = Config(str(BACKEND / "alembic.ini"))
    command.upgrade(config, "head")
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.query(RepositoryModel).delete()
    try:
        yield database_url, sessions
    finally:
        with sessions.begin() as session:
            session.query(RepositoryModel).delete()
        engine.dispose()


def test_migration_can_upgrade_and_downgrade(
    postgres: tuple[str, sessionmaker[Session]]
) -> None:
    database_url, _ = postgres
    engine = create_engine(database_url)
    config = Config(str(BACKEND / "alembic.ini"))
    command.downgrade(config, "base")
    assert not inspect(engine).has_table("repositories")
    command.upgrade(config, "head")
    assert inspect(engine).has_table("repositories")
    assert inspect(engine).has_table("edges")
    engine.dispose()


def test_repository_deletion_cascades_to_analysis_rows(
    postgres: tuple[str, sessionmaker[Session]], tmp_path: Path
) -> None:
    _, sessions = postgres
    root = tmp_path / "analysis"
    root.mkdir()
    (root / "module.py").write_text(
        "def run():\n    return helper()\n\ndef helper():\n    return 1\n",
        encoding="utf-8",
    )
    database = SqlAlchemyRepository(sessions)
    settings = Settings(ANALYSIS_ROOT=root)
    repository_id, _ = AnalyzeRepository(database, settings)(root, "cascade")

    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(FileModel)) > 0
        assert session.scalar(select(func.count()).select_from(SymbolModel)) > 0
        assert session.scalar(select(func.count()).select_from(EdgeModel)) > 0
        row = session.get(RepositoryModel, repository_id)
        assert row is not None
        session.delete(row)
        session.commit()
        assert session.scalar(select(func.count()).select_from(FileModel)) == 0
        assert session.scalar(select(func.count()).select_from(SymbolModel)) == 0
        assert session.scalar(select(func.count()).select_from(EdgeModel)) == 0


def test_failed_analysis_keeps_zero_child_rows(
    postgres: tuple[str, sessionmaker[Session]], tmp_path: Path
) -> None:
    _, sessions = postgres
    root = tmp_path / "analysis"
    root.mkdir()
    database = SqlAlchemyRepository(sessions)

    def failure(_: Path) -> None:
        raise RuntimeError("sensitive path content: C:\\private\\module.py")

    service = AnalyzeRepository(database, Settings(ANALYSIS_ROOT=root), failure)
    with pytest.raises(RuntimeError):
        service(root, "failed")

    with sessions() as session:
        row = session.scalar(select(RepositoryModel))
        assert row is not None
        assert row.status == "failed"
        assert "C:\\private" not in str(row.error)
        assert session.scalar(select(func.count()).select_from(FileModel)) == 0
        assert session.scalar(select(func.count()).select_from(SymbolModel)) == 0
        assert session.scalar(select(func.count()).select_from(EdgeModel)) == 0


def test_file_and_symbol_unique_constraints(
    postgres: tuple[str, sessionmaker[Session]]
) -> None:
    _, sessions = postgres
    with sessions.begin() as session:
        repository = RepositoryModel(name="unique", local_path="C:\\unique", status="ready")
        session.add(repository)
        session.flush()
        first = FileModel(
            repository_id=repository.id,
            path="module.py",
            loc=2,
            is_entry_point=False,
            parse_status="ok",
        )
        session.add(first)
        session.flush()
        first_file_id = first.id

    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(
            FileModel(
                repository_id=repository.id,
                path="module.py",
                loc=2,
                is_entry_point=False,
                parse_status="ok",
            )
        )

    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add_all(
            [
                SymbolModel(
                    file_id=first_file_id,
                    kind="function",
                    name="run",
                    qualified_name="module.py::run",
                    start_line=1,
                    end_line=2,
                ),
                SymbolModel(
                    file_id=first_file_id,
                    kind="function",
                    name="run",
                    qualified_name="module.py::run",
                    start_line=1,
                    end_line=2,
                ),
            ]
        )
