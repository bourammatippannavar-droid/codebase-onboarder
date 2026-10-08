import shutil
import subprocess
from pathlib import Path

BACKEND = Path(__file__).parents[1]


def test_import_linter_contract_passes_for_backend() -> None:
    result = subprocess.run(
        ["lint-imports"],
        cwd=BACKEND,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_import_linter_rejects_core_framework_dependency(tmp_path: Path) -> None:
    core = tmp_path / "onboarder" / "core"
    core.mkdir(parents=True)
    (tmp_path / "onboarder" / "__init__.py").write_text("", encoding="utf-8")
    (core / "__init__.py").write_text("", encoding="utf-8")
    (core / "bad.py").write_text("import typer\n", encoding="utf-8")
    shutil.copyfile(BACKEND / ".importlinter", tmp_path / ".importlinter")

    result = subprocess.run(
        ["lint-imports"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    assert "typer" in result.stdout + result.stderr