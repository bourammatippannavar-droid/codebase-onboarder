import json
import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from onboarder.api.app import create_app
from onboarder.bootstrap import ApplicationContainer, create_container
from onboarder.db.models import EdgeModel, FileModel, RepositoryModel, SymbolModel
from onboarder.db.repository import SqlAlchemyRepository
from onboarder.services.protocols import FileInput, SymbolInput
from onboarder.settings import Settings

BACKEND = Path(__file__).parents[1]
FIXTURE_PROJECT = BACKEND / "tests" / "fixtures" / "call_project"


@pytest.fixture
def test_database(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[str, sessionmaker[Session]]]:
    database_url = Settings().TEST_DATABASE_URL or os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is unset; API PostgreSQL test skipped")
    engine = create_engine(database_url)
    try:
        with engine.connect():
            pass
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(
            "PostgreSQL is unreachable via TEST_DATABASE_URL: "
            f"{exc.__class__.__name__}"
        )

    monkeypatch.setenv("ONBOARDER_TEST_MIGRATION", "1")
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions.begin() as session:
        session.query(RepositoryModel).delete()
    try:
        yield database_url, sessions
    finally:
        with sessions.begin() as session:
            session.query(RepositoryModel).delete()
        engine.dispose()


def _assert_safe_json(response_texts: list[str]) -> None:
    for text in response_texts:
        json.loads(text)
        assert "C:\\" not in text
        assert "Traceback" not in text


def test_postgres_api_end_to_end(test_database: tuple[str, sessionmaker[Session]]) -> None:
    database_url, _ = test_database
    settings = Settings(DATABASE_URL=database_url, ANALYSIS_ROOT=BACKEND.parent)
    container = create_container(settings)
    response_texts: list[str] = []
    with TestClient(create_app(container)) as client:
        created = client.post(
            "/api/v1/repositories",
            json={"path": str(FIXTURE_PROJECT), "name": "api-e2e"},
        )
        assert created.status_code == 202
        response_texts.append(created.text)
        repository_id = created.json()["id"]
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            current = client.get(f"/api/v1/repositories/{repository_id}")
            response_texts.append(current.text)
            assert current.status_code == 200
            status_value = current.json()["status"]
            if status_value in {"ready", "failed"}:
                break
            time.sleep(0.1)
        assert status_value == "ready", current.text

        files = client.get(f"/api/v1/repositories/{repository_id}/files")
        assert files.status_code == 200
        response_texts.append(files.text)
        file_items = files.json()["items"]
        assert file_items
        main_file = next(item for item in file_items if item["path"] == "main.py")

        dependents = client.get(
            f"/api/v1/repositories/{repository_id}/files/{main_file['id']}/dependents"
        )
        assert dependents.status_code == 200
        response_texts.append(dependents.text)

        symbols = client.get(f"/api/v1/repositories/{repository_id}/files/{main_file['id']}")
        assert symbols.status_code == 200
        response_texts.append(symbols.text)
        symbol = next(item for item in symbols.json()["symbols"] if item["name"] == "main")
        usages = client.get(
            f"/api/v1/repositories/{repository_id}/symbols/{symbol['id']}/usages"
        )
        assert usages.status_code == 200
        response_texts.append(usages.text)

        search = client.get(f"/api/v1/repositories/{repository_id}/search?q=helper")
        assert search.status_code == 200
        response_texts.append(search.text)
        for wildcard_query in ("%%", "_ _"):
            wildcard_search = client.get(
                f"/api/v1/repositories/{repository_id}/search",
                params={"q": wildcard_query},
            )
            assert wildcard_search.status_code == 200
            assert wildcard_search.json()["total"] == 0
            response_texts.append(wildcard_search.text)
        graph = client.get(f"/api/v1/repositories/{repository_id}/graph")
        assert graph.status_code == 200
        response_texts.append(graph.text)
        guide = client.get(f"/api/v1/repositories/{repository_id}/guide")
        assert guide.status_code == 200
        response_texts.append(guide.text)
        missing = client.get(
            f"/api/v1/repositories/{repository_id}/files/{'00000000-0000-0000-0000-000000000000'}"
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == "file_not_found"
        response_texts.append(missing.text)

    _assert_safe_json(response_texts)


def test_background_error_marks_failed_and_clears_all_partial_rows(
    test_database: tuple[str, sessionmaker[Session]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from onboarder import bootstrap

    database_url, sessions = test_database
    root = tmp_path / "allowed"
    root.mkdir()
    settings = Settings(DATABASE_URL=database_url, ANALYSIS_ROOT=root)
    repository = SqlAlchemyRepository(sessions)
    pending = repository.create_pending("failure", root)

    class BrokenAnalysis:
        def __init__(self, active_repository: SqlAlchemyRepository, _: Settings) -> None:
            self.repository = active_repository

        def run_registered(self, repository_id: object, path: Path) -> None:
            self.repository.mark_running(repository_id)
            self.repository.complete_analysis(
                repository_id,
                (FileInput("partial.py", 1, False, "ok"),),
                (
                    SymbolInput(
                        "partial.py", "function", "partial", "partial.py::partial", 1, 1
                    ),
                ),
                (),
                {"files": 1},
            )
            raise RuntimeError(f"Traceback {path}")

    monkeypatch.setattr(bootstrap, "AnalyzeRepository", BrokenAnalysis)
    container: ApplicationContainer = create_container(settings)
    container._run_analysis(pending.id, root, "failure-test")

    with sessions() as session:
        row = session.get(RepositoryModel, pending.id)
        assert row is not None
        assert row.status == "failed"
        assert row.error == "Analysis failed (RuntimeError)"
        assert session.query(FileModel).filter_by(repository_id=pending.id).count() == 0
        assert session.query(SymbolModel).count() == 0
        assert session.query(EdgeModel).count() == 0
    container.shutdown()
