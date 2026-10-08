from pathlib import Path

import pytest
from typer.testing import CliRunner

from onboarder.cli import app
from onboarder.parser import parse_python_file
from onboarder.scanner import MAX_FILE_SIZE, find_python_files

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_PROJECT = FIXTURES / "sample_project"


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
    assert "Syntax error: line " in result.output
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
    target = tmp_path / "target.py"
    target.write_text("pass\n", encoding="utf-8")
    linked_file = tmp_path / "linked.py"
    linked_directory = tmp_path / "linked_directory"
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