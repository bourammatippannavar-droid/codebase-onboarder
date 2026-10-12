from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_api import FakeContainer, _assert_problem

from onboarder.api.app import create_app
from onboarder.services.protocols import EdgeRecord, FileRecord


@pytest.fixture
def module_client(tmp_path: Path) -> Any:
    root = tmp_path / "analysis"
    root.mkdir()
    container = FakeContainer(root)
    with TestClient(create_app(container), raise_server_exceptions=False) as client:
        client.container = container
        yield client


def _module_url(client: Any) -> str:
    return (
        f"/api/v1/repositories/{client.container.repository.repository_id}"
        "/graph/modules"
    )


def _add_files(
    client: Any, specifications: tuple[tuple[str, int, bool], ...]
) -> dict[str, FileRecord]:
    repository = client.container.repository
    repository.files = tuple(
        FileRecord(
            uuid4(),
            repository.repository_id,
            path,
            loc,
            entry_point,
            "ok",
        )
        for path, loc, entry_point in specifications
    )
    return {item.path: item for item in repository.files}


def _edge(repository_id: Any, source: FileRecord, target: FileRecord) -> EdgeRecord:
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


def test_module_graph_aggregates_top_level_and_collapses_outside(module_client: Any) -> None:
    files = _add_files(
        module_client,
        (
            ("main.py", 10, True),
            ("pkg/a.py", 20, False),
            ("pkg/sub/b.py", 30, False),
            ("tests/test_hidden.py", 100, False),
        ),
    )
    repository = module_client.container.repository
    repository.edges = (
        _edge(repository.repository_id, files["main.py"], files["pkg/a.py"]),
    )

    response = module_client.get(_module_url(module_client))
    assert response.status_code == 200
    graph = response.json()
    nodes = {node["path"]: node for node in graph["nodes"]}
    assert nodes["pkg"] == {
        "id": "folder:pkg",
        "kind": "folder",
        "name": "pkg",
        "path": "pkg",
        "file_count": 2,
        "loc": 50,
        "in_cycle": False,
    }
    assert "main.py" in nodes
    assert "tests" not in nodes
    assert graph["edges"] == [
        {
            "source": "file:" + str(files["main.py"].id),
            "target": "folder:pkg",
            "count": 1,
            "in_cycle": False,
        }
    ]
    nested = module_client.get(
        _module_url(module_client), params={"path_prefix": "pkg"}
    ).json()
    nested_nodes = {node["path"]: node for node in nested["nodes"]}
    assert nested_nodes["pkg/a.py"]["kind"] == "file"
    assert nested_nodes["pkg/sub"]["file_count"] == 1
    assert nested["edges"][0]["source"] == "outside:(root)"


def test_module_graph_empty_and_nonexistent_prefix_return_empty(module_client: Any) -> None:
    _add_files(module_client, (("src/a.py", 5, False),))
    for prefix in ("empty", "not/here"):
        response = module_client.get(
            _module_url(module_client), params={"path_prefix": prefix}
        )
        assert response.status_code == 200
        assert response.json() == {
            "nodes": [],
            "edges": [],
            "truncated": False,
            "total_nodes": 0,
        }


@pytest.mark.parametrize(
    "path_prefix",
    ("../secret", "src/../../secret", "/src", "C:/src", "src\\pkg"),
)
def test_module_graph_rejects_unsafe_prefixes(
    module_client: Any, path_prefix: str
) -> None:
    _assert_problem(
        module_client.get(
            _module_url(module_client), params={"path_prefix": path_prefix}
        ),
        "validation_error",
        422,
    )


def test_module_graph_marks_cycles_and_caps_largest_nodes(module_client: Any) -> None:
    paths = tuple(
        (f"{index:03}.py", 1000 + index if index < 2 else index + 1, False)
        for index in range(151)
    )
    files = _add_files(module_client, paths)
    repository = module_client.container.repository
    repository.edges = (
        _edge(repository.repository_id, files["000.py"], files["001.py"]),
        _edge(repository.repository_id, files["001.py"], files["000.py"]),
    )

    response = module_client.get(_module_url(module_client))
    graph = response.json()
    assert graph["truncated"] is True
    assert graph["total_nodes"] == 151
    assert len(graph["nodes"]) == 150
    assert graph["nodes"][0]["path"] == "001.py"
    cycle_nodes = {
        node["path"] for node in graph["nodes"] if node["in_cycle"]
    }
    assert cycle_nodes == {"000.py", "001.py"}
    assert all(edge["in_cycle"] for edge in graph["edges"])


def test_module_graph_rejects_repository_that_is_not_ready(module_client: Any) -> None:
    module_client.container.repository.status = "pending"
    _assert_problem(
        module_client.get(_module_url(module_client)),
        "repository_not_ready",
        409,
    )
