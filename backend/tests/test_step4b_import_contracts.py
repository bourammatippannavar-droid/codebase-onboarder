import shutil
import subprocess
from pathlib import Path

BACKEND = Path(__file__).parents[1]


def _lint_violation(
    tmp_path: Path,
    package: str,
    dependency: str,
    lint_imports_executable: Path,
) -> subprocess.CompletedProcess[str]:
    shutil.copyfile(BACKEND / ".importlinter", tmp_path / ".importlinter")
    root = tmp_path / "onboarder"
    root.mkdir()
    (root / "__init__.py").write_text("", encoding="utf-8")
    (root / "core").mkdir()
    (root / "core" / "__init__.py").write_text("", encoding="utf-8")
    for module in ("core", "services", "db"):
        package_path = root / module
        package_path.mkdir(exist_ok=True)
        (package_path / "__init__.py").write_text("", encoding="utf-8")
    source = root / package
    (source / "bad.py").write_text(f"import {dependency}\n", encoding="utf-8")
    return subprocess.run(
        [str(lint_imports_executable)],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
    )


def test_import_linter_rejects_services_database_dependency(
    tmp_path: Path, lint_imports_executable: Path
) -> None:
    result = _lint_violation(
        tmp_path, "services", "onboarder.db", lint_imports_executable
    )

    assert result.returncode != 0
    assert "services" in result.stdout.lower() + result.stderr.lower()


def test_import_linter_rejects_database_api_dependency(
    tmp_path: Path, lint_imports_executable: Path
) -> None:
    result = _lint_violation(tmp_path, "db", "fastapi", lint_imports_executable)

    assert result.returncode != 0
    assert "fastapi" in result.stdout.lower() + result.stderr.lower()
