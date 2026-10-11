from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from test_api import FakeContainer, _assert_problem

from onboarder.api.app import create_app
from onboarder.services.protocols import EdgeRecord, FileRecord


@pytest.fixture
def service_client(tmp_path: Path) -> Any:
    root = tmp_path / "analysis"
    root.mkdir()
    container = FakeContainer(root)
    with TestClient(create_app(container), raise_server_exceptions=False) as client:
        client.container = container
        yield client


def _repository_url(client: Any) -> str:
    return f"/api/v1/repositories/{client.container.repository.repository_id}"


def _import_edge(
    repository_id: UUID, source: FileRecord, target: FileRecord
) -> EdgeRecord:
    return EdgeRecord(
        uuid4(),
        repository_id,
        "IMPORTS",
        source.id,
        source.path,
        None,
        None,
        target.id,
        target.path,
        None,
        None,
        target.path,
        "exact",
        None,
        False,
        1,
    )


def test_source_reads_only_repository_file_and_rejects_escapes(
    service_client: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Windows denies symlink creation, Path.resolve is patched to simulate it."""
    client = service_client
    repository = client.container.repository
    root = client.container.settings.ANALYSIS_ROOT
    (root / "main.py").write_bytes(b"print('ok')\n")
    url = _repository_url(client)
    file_id = repository.file_main

    response = client.get(f"{url}/files/{file_id}/source")
    assert response.status_code == 200
    assert response.json() == {
        "path": "main.py",
        "language": "python",
        "content": "print('ok')\n",
        "line_count": 1,
    }
    (root / "main.py").write_bytes(b"\xff")
    replacement = client.get(f"{url}/files/{file_id}/source")
    assert replacement.status_code == 200
    assert replacement.json()["content"] == "\ufffd"

    other_repository_file = FileRecord(
        uuid4(), uuid4(), "main.py", 1, False, "ok"
    )
    repository.files = (*repository.files, other_repository_file)
    _assert_problem(
        client.get(f"{url}/files/{other_repository_file.id}/source"),
        "file_not_found",
        404,
    )

    repository.files = tuple(
        FileRecord(
            item.id,
            item.repository_id,
            "../secret.py" if item.id == file_id else item.path,
            item.loc,
            item.is_entry_point,
            item.parse_status,
        )
        for item in repository.files
        if item.repository_id == repository.repository_id
    )
    (root.parent / "secret.py").write_text("secret", encoding="utf-8")
    _assert_problem(client.get(f"{url}/files/{file_id}/source"), "file_not_found", 404)

    outside = tmp_path / "private.py"
    outside.write_text("secret", encoding="utf-8")
    link_path = root / "linked.py"
    try:
        link_path.symlink_to(outside)
    except OSError:
        original_resolve = Path.resolve

        def simulated_resolve(
            path: Path, strict: bool = False
        ) -> Path:
            if path == link_path:
                return outside.resolve()
            return original_resolve(path, strict=strict)

        monkeypatch.setattr(Path, "resolve", simulated_resolve)
    linked = FileRecord(uuid4(), repository.repository_id, "linked.py", 1, False, "ok")
    repository.files = (*repository.files, linked)
    _assert_problem(client.get(f"{url}/files/{linked.id}/source"), "file_not_found", 404)


def test_source_rejects_large_binary_and_not_ready_files(service_client: Any) -> None:
    client = service_client
    repository = client.container.repository
    root = client.container.settings.ANALYSIS_ROOT
    url = _repository_url(client)

    (root / "main.py").write_bytes(b"x" * (1_048_576 + 1))
    _assert_problem(
        client.get(f"{url}/files/{repository.file_main}/source"),
        "file_too_large",
        413,
    )

    (root / "main.py").write_bytes(b"print('ok')\x00")
    _assert_problem(
        client.get(f"{url}/files/{repository.file_main}/source"),
        "binary_file",
        415,
    )

    repository.status = "pending"
    _assert_problem(
        client.get(f"{url}/files/{repository.file_main}/source"),
        "repository_not_ready",
        409,
    )
    _assert_problem(client.get(f"{url}/overview"), "repository_not_ready", 409)


def test_overview_handles_empty_repository_and_empty_call_edges(service_client: Any) -> None:
    client = service_client
    repository = client.container.repository
    repository.files = ()
    repository.symbols = ()
    repository.edges = ()

    response = client.get(f"{_repository_url(client)}/overview")
    assert response.status_code == 200
    assert response.json() == {
        "files": 0,
        "symbols": 0,
        "loc": 0,
        "cycle_count": 0,
        "folders": [],
        "call_confidence": {"exact": 0, "inferred": 0, "unresolved": 0},
        "resolution_rate": None,
        "hotspots": [],
        "reading_order": [],
    }


def test_overview_cycles_and_hotspot_ordering_are_stable(service_client: Any) -> None:
    client = service_client
    repository = client.container.repository
    repository.files = tuple(
        FileRecord(uuid4(), repository.repository_id, f"{name}.py", loc, name == "a", "ok")
        for name, loc in (
            ("a", 10),
            ("b", 20),
            ("c", 30),
            ("d", 40),
            ("e", 50),
            ("f", 60),
            ("g", 70),
        )
    )
    files = {Path(item.path).stem: item for item in repository.files}
    repository.edges = (
        _import_edge(repository.repository_id, files["a"], files["b"]),
        _import_edge(repository.repository_id, files["b"], files["a"]),
        _import_edge(repository.repository_id, files["c"], files["a"]),
        _import_edge(repository.repository_id, files["d"], files["c"]),
        _import_edge(repository.repository_id, files["e"], files["a"]),
        _import_edge(repository.repository_id, files["f"], files["a"]),
        _import_edge(repository.repository_id, files["g"], files["a"]),
    )

    response = client.get(f"{_repository_url(client)}/overview")
    assert response.status_code == 200
    result = response.json()
    assert result["cycle_count"] == 2
    hotspots = result["hotspots"]
    assert [(item["path"], item["blast_radius"]) for item in hotspots[:4]] == [
        ("a.py", 6),
        ("b.py", 6),
        ("c.py", 1),
        ("d.py", 0),
    ]
    assert "cycle" in hotspots[0]["flags"]
    assert "central" in hotspots[0]["flags"]
    assert result["folders"] == [{"name": "(root)", "loc": 280, "files": 7}]
