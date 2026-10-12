from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_api import FakeContainer, _assert_problem

from onboarder.api.app import create_app
from onboarder.services.protocols import EdgeRecord, FileRecord


@pytest.fixture
def explorer_client(tmp_path: Path) -> Any:
    root = tmp_path / "analysis"
    root.mkdir()
    container = FakeContainer(root)
    repository = container.repository
    repository.files = (
        FileRecord(repository.file_main, repository.repository_id, "main.py", 4, True, "ok"),
        FileRecord(repository.file_helper, repository.repository_id, "helpers.py", 2, False, "ok"),
        FileRecord(uuid4(), repository.repository_id, "src/one.py", 7, False, "ok"),
        FileRecord(uuid4(), repository.repository_id, "src/nested/two.py", 9, False, "syntax_error"),
        FileRecord(uuid4(), repository.repository_id, "tests/test_sample.py", 3, False, "skipped"),
    )
    with TestClient(create_app(container), raise_server_exceptions=False) as client:
        client.container = container
        yield client


def _repository_url(client: Any) -> str:
    return f"/api/v1/repositories/{client.container.repository.repository_id}"


def test_tree_returns_immediate_children_and_syncable_relative_paths(
    explorer_client: Any,
) -> None:
    client = explorer_client
    root = client.get(f"{_repository_url(client)}/tree")
    assert root.status_code == 200
    assert root.json() == {
        "folders": [
            {"name": "src", "path": "src", "file_count": 2},
            {"name": "tests", "path": "tests", "file_count": 1},
        ],
        "files": [
            {
                "file_id": str(client.container.repository.file_helper),
                "name": "helpers.py",
                "path": "helpers.py",
                "loc": 2,
                "parse_status": "ok",
            },
            {
                "file_id": str(client.container.repository.file_main),
                "name": "main.py",
                "path": "main.py",
                "loc": 4,
                "parse_status": "ok",
            },
        ],
    }

    nested = client.get(
        f"{_repository_url(client)}/tree", params={"path_prefix": "src"}
    ).json()
    assert nested == {
        "folders": [{"name": "nested", "path": "src/nested", "file_count": 1}],
        "files": [
            {
                "file_id": str(client.container.repository.files[2].id),
                "name": "one.py",
                "path": "src/one.py",
                "loc": 7,
                "parse_status": "ok",
            }
        ],
    }


@pytest.mark.parametrize(
    "path_prefix",
    ("../outside", "src/../../outside", "/src", "C:/src", "src\\nested"),
)
def test_tree_rejects_unsafe_prefixes(explorer_client: Any, path_prefix: str) -> None:
    _assert_problem(
        explorer_client.get(
            f"{_repository_url(explorer_client)}/tree",
            params={"path_prefix": path_prefix},
        ),
        "validation_error",
        422,
    )


def test_tree_and_symbol_relationships_require_ready_repository(
    explorer_client: Any,
) -> None:
    client = explorer_client
    client.container.repository.status = "running"
    _assert_problem(
        client.get(f"{_repository_url(client)}/tree"),
        "repository_not_ready",
        409,
    )


def test_file_detail_includes_symbols_and_relationship_confidence_pagination(
    explorer_client: Any,
) -> None:
    client = explorer_client
    repository = client.container.repository
    repository.edges = (
        *repository.edges,
        EdgeRecord(
            uuid4(),
            repository.repository_id,
            "CALLS",
            repository.file_main,
            "main.py",
            repository.symbol_main,
            "main.py::main",
            repository.file_helper,
            "helpers.py",
            repository.symbol_helper,
            "helpers.py::helper",
            "helper",
            "exact",
            None,
            False,
            4,
        ),
    )
    url = _repository_url(client)
    file_detail = client.get(f"{url}/files/{repository.file_helper}")
    assert file_detail.status_code == 200
    symbol = file_detail.json()["symbols"][0]
    assert {
        "kind",
        "name",
        "qualified_name",
        "start_line",
        "end_line",
    } <= symbol.keys()

    usages_url = f"{url}/symbols/{repository.symbol_helper}/usages"
    default = client.get(usages_url)
    assert default.status_code == 200
    assert default.json()["total"] == 2
    assert {edge["confidence"] for edge in default.json()["items"]} == {
        "exact",
        "inferred",
    }

    exact = client.get(usages_url, params={"min_confidence": "exact"})
    assert exact.json()["total"] == 1
    assert exact.json()["items"][0]["confidence"] == "exact"
    all_confidences = client.get(
        usages_url,
        params={"min_confidence": "unresolved", "limit": 1, "offset": 1},
    )
    assert all_confidences.json()["total"] == 2
    assert len(all_confidences.json()["items"]) == 1
    assert all_confidences.json()["items"][0]["id"] != default.json()["items"][0]["id"]

    for relation in ("callers", "callees"):
        response = client.get(
            f"{url}/symbols/{repository.symbol_helper}/{relation}",
            params={"min_confidence": "exact", "limit": 1, "offset": 0},
        )
        assert response.status_code == 200
        assert "total" in response.json()

    search = client.get(f"{url}/search", params={"q": "helper"})
    assert search.status_code == 200
    assert any(
        item["symbol_kind"] == "function"
        for item in search.json()["items"]
        if item["kind"] == "symbol"
    )

    _assert_problem(
        client.get(usages_url, params={"min_confidence": "external"}),
        "validation_error",
        422,
    )


def test_file_import_relationships_return_confident_line_annotated_edges(
    explorer_client: Any,
) -> None:
    client = explorer_client
    repository = client.container.repository
    url = f"{_repository_url(client)}/files/{repository.file_helper}"

    imports = client.get(f"{url}/imported-by")
    assert imports.status_code == 200
    assert imports.json()["total"] == 1
    edge = imports.json()["items"][0]
    assert edge["src_file"] == "main.py"
    assert edge["confidence"] == "exact"
    assert edge["line"] == 1

    import_targets = client.get(f"{_repository_url(client)}/files/{repository.file_main}/imports")
    assert import_targets.status_code == 200
    assert import_targets.json()["items"][0]["dst_file"] == "helpers.py"
