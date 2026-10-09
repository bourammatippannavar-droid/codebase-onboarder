from concurrent.futures import Future
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from onboarder.api.app import create_app
from onboarder.bootstrap import AnalysisSchedulingError
from onboarder.services.api import OnboarderAPI, RepositoryBusyError
from onboarder.services.protocols import (
    AnalysisSnapshot,
    EdgeRecord,
    FileRecord,
    RepositorySummary,
    SearchRecord,
    SymbolRecord,
)
from onboarder.settings import Settings


class FakeRepository:
    def __init__(self, root: Path) -> None:
        now = datetime.now(UTC)
        self.root = root
        self.repository_id = uuid4()
        self.file_main = uuid4()
        self.file_helper = uuid4()
        self.symbol_main = uuid4()
        self.symbol_helper = uuid4()
        self.summary = RepositorySummary(
            self.repository_id, "fixture", root, "ready", None, {},
            now, now,
        )
        self.files = (
            FileRecord(self.file_main, self.repository_id, "main.py", 4, True, "ok"),
            FileRecord(self.file_helper, self.repository_id, "helpers.py", 2, False, "ok"),
        )
        self.symbols = (
            SymbolRecord(
                self.symbol_main, self.file_main, "main.py", "function", "main",
                "main.py::main", 1, 4
            ),
            SymbolRecord(
                self.symbol_helper, self.file_helper, "helpers.py", "function", "helper",
                "helpers.py::helper", 1, 2
            ),
        )
        self.edges = (
            EdgeRecord(
                uuid4(), self.repository_id, "IMPORTS", self.file_main, "main.py",
                None, None, self.file_helper, "helpers.py", None, None, "helpers",
                "exact", None, False, 1
            ),
            EdgeRecord(
                uuid4(), self.repository_id, "CALLS", self.file_main, "main.py",
                self.symbol_main, "main.py::main", self.file_helper, "helpers.py",
                self.symbol_helper, "helpers.py::helper", "helper", "inferred",
                None, False, 3
            ),
        )
        self.status = "ready"
        self.pending: dict[UUID, RepositorySummary] = {}
        self.search_calls: list[str] = []
        self.recovered = False
        self.fail_create = False

    def list_repositories(self) -> tuple[RepositorySummary, ...]:
        return (self._summary(),)

    def get_repository(self, repository_id: UUID) -> RepositorySummary | None:
        return self._summary() if repository_id == self.repository_id else None

    def get_analysis(self, repository_id: UUID) -> AnalysisSnapshot | None:
        if repository_id != self.repository_id:
            return None
        return AnalysisSnapshot(self._summary(), self.files, self.symbols, self.edges)

    def create_pending(self, name: str, local_path: Path) -> RepositorySummary:
        if self.fail_create:
            raise RepositoryBusyError
        if self.status in {"pending", "running"}:
            raise RepositoryBusyError
        now = datetime.now(UTC)
        self.repository_id = uuid4()
        self.root = local_path
        self.status = "pending"
        self.summary = RepositorySummary(
            self.repository_id, name, local_path, "pending", None, {}, now, None
        )
        return self.summary

    def delete_repository(self, repository_id: UUID) -> bool:
        if repository_id != self.repository_id:
            return False
        if self.status in {"pending", "running"}:
            raise RepositoryBusyError
        self.status = "deleted"
        return True

    def recover_interrupted(self) -> None:
        self.recovered = True
        if self.status in {"pending", "running"}:
            self.status = "failed"
            self.summary = RepositorySummary(
                self.summary.id,
                self.summary.name,
                self.root,
                "failed",
                "interrupted",
                self.summary.stats,
                self.summary.created_at,
                datetime.now(UTC),
            )

    def mark_running(self, repository_id: UUID) -> None:
        if repository_id == self.repository_id:
            self.status = "running"

    def fail_analysis(self, repository_id: UUID, error: str) -> None:
        if repository_id == self.repository_id:
            self.status = "failed"

    def complete_analysis(self, *args: Any, **kwargs: Any) -> None:
        self.status = "ready"

    def start_analysis(self, name: str, local_path: Path) -> UUID:
        self.status = "running"
        return self.repository_id

    def search(
        self, repository_id: UUID, pattern: str, limit: int, offset: int
    ) -> tuple[tuple[SearchRecord, ...], int]:
        self.search_calls.append(pattern)
        literal = pattern[1:-1].replace("\\%", "%").replace("\\_", "_").replace("\\\\", "\\")
        records = [
            SearchRecord("file", item.id, item.path, item.path, None, None)
            for item in self.files
            if literal.casefold() in item.path.casefold()
        ]
        records.extend(
            SearchRecord(
                "symbol", item.file_id, item.file_path, item.name,
                item.qualified_name, item.id
            )
            for item in self.symbols
            if literal.casefold() in item.name.casefold()
            or literal.casefold() in item.qualified_name.casefold()
        )
        records.sort(key=lambda item: (item.path, item.kind, item.name))
        return tuple(records[offset : offset + limit]), len(records)

    def ping(self) -> None:
        return None

    def _summary(self) -> RepositorySummary:
        return RepositorySummary(
            self.summary.id, self.summary.name, self.root, self.status,
            self.summary.error, self.summary.stats, self.summary.created_at,
            self.summary.finished_at
        )


class FakeContainer:
    def __init__(self, root: Path, status: str = "ready") -> None:
        self.repository = FakeRepository(root)
        self.repository.status = status
        self.api = OnboarderAPI(
            self.repository,
            Settings(
                DATABASE_URL="postgresql+psycopg://unused/unused",
                ANALYSIS_ROOT=root,
            ),
        )
        self.settings = self.api.settings
        self.submitted: list[tuple[UUID, Path, str]] = []
        self.fail_submit = False

    def submit_analysis(self, repository_id: UUID, path: Path, request_id: str) -> Future[None]:
        self.submitted.append((repository_id, path, request_id))
        if self.fail_submit:
            raise AnalysisSchedulingError
        future: Future[None] = Future()
        return future

    def recover_interrupted(self) -> None:
        self.repository.recover_interrupted()

    def shutdown(self) -> None:
        return None


@pytest.fixture
def client(tmp_path: Path) -> Any:
    root = tmp_path / "allowed"
    root.mkdir()
    container = FakeContainer(root)
    with TestClient(create_app(container), raise_server_exceptions=False) as test_client:
        test_client.container = container
        yield test_client


def _repo_path(client: Any) -> str:
    return f"/api/v1/repositories/{client.container.repository.repository_id}"


def _assert_problem(response: Any, code: str, status: int) -> None:
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == code
    assert body["status"] == status
    assert set(body) == {"type", "title", "status", "detail", "code", "request_id"}
    assert body["request_id"] == response.headers["x-request-id"]
    assert "Traceback" not in response.text
    assert "C:\\" not in response.text


def test_api_success_endpoints_include_pagination_edges_and_safe_paths(client: Any) -> None:
    repo = _repo_path(client)
    listed = client.get("/api/v1/repositories", headers={"X-Request-ID": "test-req"})
    assert listed.status_code == 200
    assert listed.headers["x-request-id"] == "test-req"
    assert listed.json()[0]["path"] == "."
    assert "C:\\" not in listed.text
    assert client.get(repo).status_code == 200

    files = client.get(f"{repo}/files?limit=1")
    assert files.json()["total"] == 2
    assert len(files.json()["items"]) == 1
    file_id = client.container.repository.file_main
    file_detail = client.get(f"{repo}/files/{file_id}")
    assert file_detail.status_code == 200
    assert len(file_detail.json()["symbols"]) == 1
    assert client.get(f"{repo}/files/{file_id}/dependencies").json()["total"] == 1
    assert client.get(f"{repo}/files/{file_id}/dependents").json()["total"] == 0

    symbol_id = client.container.repository.symbol_helper
    usages = client.get(f"{repo}/symbols/{symbol_id}/usages")
    assert usages.json()["total"] == 1
    assert usages.json()["items"][0]["confidence"] == "inferred"
    for kind in ("callers", "callees"):
        edge_response = client.get(f"{repo}/symbols/{symbol_id}/{kind}")
        assert edge_response.status_code == 200
        for edge in edge_response.json()["items"]:
            assert "confidence" in edge and "origin" in edge and "is_constructor" in edge

    assert client.get(f"{repo}/search?q=he").json()["total"] >= 1
    graph = client.get(f"{repo}/graph").json()
    assert graph["total_nodes"] == 2
    assert graph["total_edges"] == 2
    assert all("confidence" in edge for edge in graph["edges"])
    assert client.get(f"{repo}/guide").status_code == 200
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}

    deleted = client.delete(repo)
    assert deleted.status_code == 204


def test_post_returns_pending_and_rejects_duplicate_path(client: Any) -> None:
    root = client.container.settings.ANALYSIS_ROOT
    response = client.post(
        "/api/v1/repositories",
        json={"path": str(root), "name": "queued"},
        headers={"X-Request-ID": "queue-1"},
    )
    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert client.container.submitted[0][2] == "queue-1"
    _assert_problem(
        client.post("/api/v1/repositories", json={"path": str(root), "name": "duplicate"}),
        "repository_busy",
        409,
    )


def test_every_analysis_read_route_rejects_not_ready(client: Any) -> None:
    client.container.repository.status = "pending"
    repo = _repo_path(client)
    file_id = client.container.repository.file_main
    symbol_id = client.container.repository.symbol_main
    paths = [
        f"{repo}/files",
        f"{repo}/files/{file_id}",
        f"{repo}/files/{file_id}/dependents",
        f"{repo}/files/{file_id}/dependencies",
        f"{repo}/symbols/{symbol_id}/usages",
        f"{repo}/symbols/{symbol_id}/callers",
        f"{repo}/symbols/{symbol_id}/callees",
        f"{repo}/search?q=he",
        f"{repo}/graph",
        f"{repo}/guide",
    ]
    for path in paths:
        _assert_problem(client.get(path), "repository_not_ready", 409)


def test_errors_validation_not_found_busy_and_internal_are_problem_details(client: Any) -> None:
    repo = _repo_path(client)
    _assert_problem(
        client.get(f"/api/v1/repositories/{uuid4()}"),
        "repository_not_found",
        404,
    )
    _assert_problem(
        client.get(f"{repo}/files/{uuid4()}"),
        "file_not_found",
        404,
    )
    _assert_problem(
        client.get(f"{repo}/symbols/{uuid4()}/usages"),
        "symbol_not_found",
        404,
    )
    _assert_problem(
        client.get(f"{repo}/search?q=x"),
        "validation_error",
        422,
    )
    _assert_problem(
        client.get(f"{repo}/graph?max_nodes=151"),
        "validation_error",
        422,
    )
    _assert_problem(
        client.get(f"{repo}/files?limit=201"),
        "validation_error",
        422,
    )
    _assert_problem(
        client.post("/api/v1/repositories", json={"path": "bad"}),
        "validation_error",
        422,
    )

    client.container.repository.status = "running"
    _assert_problem(client.delete(repo), "repository_busy", 409)
    _assert_problem(
        client.post(
            "/api/v1/repositories",
            json={"path": str(client.container.settings.ANALYSIS_ROOT), "name": "busy"},
        ),
        "repository_busy",
        409,
    )

    client.container.repository.status = "ready"
    client.container.fail_submit = True
    _assert_problem(
        client.post(
            "/api/v1/repositories",
            json={"path": str(client.container.settings.ANALYSIS_ROOT), "name": "error"},
        ),
        "analysis_failed",
        500,
    )


def test_path_escape_and_unexpected_errors_are_sanitized(client: Any, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    _assert_problem(
        client.post(
            "/api/v1/repositories",
            json={"path": str(outside), "name": "escape"},
        ),
        "path_outside_root",
        400,
    )

    client.container.api.files = lambda *_: (_ for _ in ()).throw(
        RuntimeError("Traceback C:\\private\\file.py")
    )
    response = client.get(f"{_repo_path(client)}/files")
    _assert_problem(response, "internal_error", 500)


def test_search_escapes_like_wildcards_and_graph_has_hard_cap(client: Any) -> None:
    repo = _repo_path(client)
    wildcard = client.get(f"{repo}/search", params={"q": "%%"})
    underscore = client.get(f"{repo}/search", params={"q": "_ _"})
    assert wildcard.json()["total"] == 0
    assert underscore.json()["total"] == 0
    assert client.container.repository.search_calls[-2:] == [r"%\%\%%", r"%\_ \_%"]

    original = client.container.repository.get_analysis
    file_rows = tuple(
        FileRecord(uuid4(), client.container.repository.repository_id, f"{i}.py", 1, False, "ok")
        for i in range(151)
    )
    client.container.repository.files = file_rows
    graph = client.get(f"{repo}/graph?max_nodes=150").json()
    assert graph["truncated"] is True
    assert len(graph["nodes"]) == 150
    assert graph["total_nodes"] == 151
    client.container.repository.get_analysis = original


@pytest.mark.parametrize("status_value", ["pending", "running"])
def test_startup_marks_pending_and_running_as_interrupted(
    tmp_path: Path, status_value: str
) -> None:
    root = tmp_path / "allowed"
    root.mkdir()
    container = FakeContainer(root, status=status_value)
    with TestClient(create_app(container)):
        assert container.repository.recovered
        assert container.repository.status == "failed"
    repository = container.api.get_repository(container.repository.repository_id)
    assert repository.status == "failed"
    assert repository.error == "interrupted"
