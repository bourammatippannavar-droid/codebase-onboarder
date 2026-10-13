from pathlib import Path

import pytest
from typer.testing import CliRunner

from onboarder.cli import app
from onboarder.core.parser import parse_python_file
from onboarder.core.scanner import MAX_FILE_SIZE, find_python_files

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_PROJECT = FIXTURES / "sample_project"
GRAPH_PROJECT = FIXTURES / "graph_project"


def test_parser_extracts_classes_functions_and_imports() -> None:
    parsed = parse_python_file(SAMPLE_PROJECT / "app.py")

    assert parsed.error is None
    assert parsed.classes == ("Greeter",)
    assert parsed.functions == ("fetch_message", "greet")
    assert parsed.imports == ("import os", "from pathlib import Path as FilePath")


def test_syntax_error_is_reported_and_scan_continues() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["scan", str(SAMPLE_PROJECT)])

    assert result.exit_code == 0
    assert "broken.py\n  Syntax error: line 1:" in result.output
    assert "app.py" in result.output


def test_scanner_skips_named_directories_and_oversized_files(tmp_path: Path) -> None:
    (tmp_path / "included.py").write_text("pass\n", encoding="utf-8")
    for directory in (".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"):
        skipped = tmp_path / directory
        skipped.mkdir()
        (skipped / "ignored.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "large.py").write_bytes(b"x" * (MAX_FILE_SIZE + 1))

    assert find_python_files(tmp_path) == [tmp_path / "included.py"]


def test_scanner_skips_symlinked_files_and_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise real links where possible and simulate them when creation is restricted."""
    target = tmp_path / "target.py"
    target.write_text("pass\n", encoding="utf-8")
    linked_file = tmp_path / "linked.py"
    linked_directory = tmp_path / "linked_directory"
    try:
        linked_file.symlink_to(target)
        linked_directory.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        for link in (linked_file, linked_directory):
            if link.is_symlink():
                link.unlink()
        linked_file.write_text("pass\n", encoding="utf-8")
        linked_directory.mkdir()
        (linked_directory / "nested.py").write_text("pass\n", encoding="utf-8")
        original_is_symlink = Path.is_symlink
        symlink_paths = {linked_file, linked_directory}

        def is_symlink(path: Path) -> bool:
            return path in symlink_paths or original_is_symlink(path)

        monkeypatch.setattr(Path, "is_symlink", is_symlink)

    assert find_python_files(tmp_path) == [target]


def test_scan_does_not_execute_fixture_files() -> None:
    canary = SAMPLE_PROJECT / "canary_created.txt"
    assert not canary.exists()

    result = CliRunner().invoke(app, ["scan", str(SAMPLE_PROJECT)])

    assert result.exit_code == 0
    assert not canary.exists()


def test_parser_records_symbol_locations_and_main_guard() -> None:
    parsed = parse_python_file(
        GRAPH_PROJECT / "symbols.py", project_root=GRAPH_PROJECT
    )

    assert [
        (symbol.kind, symbol.name, symbol.qualified_name, symbol.start_line, symbol.end_line)
        for symbol in parsed.symbols
    ] == [
        ("class", "Outer", "symbols.py::Outer", 1, 3),
        ("method", "method", "symbols.py::Outer.method", 2, 3),
        ("function", "top_level", "symbols.py::top_level", 6, 7),
    ]
    assert parsed.has_main_guard


def test_cli_deps_shows_each_resolution_status() -> None:
    result = CliRunner().invoke(app, ["deps", str(GRAPH_PROJECT), "main.py"])

    assert result.exit_code == 0
    assert "exact" in result.output
    assert "external" in result.output
    assert "unresolved" in result.output
    assert "stdlib" in result.output
    assert "third-party" in result.output
    assert "\\" not in result.output


def test_cli_used_by_supports_transitive_depth() -> None:
    result = CliRunner().invoke(
        app,
        ["used-by", str(GRAPH_PROJECT), "chain/base.py", "--transitive", "--depth", "2"],
    )

    assert result.exit_code == 0
    assert "chain/middle.py" in result.output
    assert "chain/top.py" in result.output


def test_cli_cycles_lists_cycle_members() -> None:
    result = CliRunner().invoke(app, ["cycles", str(GRAPH_PROJECT)])

    assert result.exit_code == 0
    assert "pkg/alpha.py" in result.output
    assert "pkg/beta.py" in result.output