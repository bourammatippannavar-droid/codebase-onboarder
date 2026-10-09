import shutil
import subprocess
from pathlib import Path

BACKEND = Path(__file__).parents[1]


def test_import_linter_rejects_api_core_import(tmp_path: Path) -> None:
    shutil.copyfile(BACKEND / ".importlinter", tmp_path / ".importlinter")
    root = tmp_path / "onboarder"
    for name in ("", "api", "core", "db", "services"):
        package = root / name
        package.mkdir(parents=True, exist_ok=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
    (root / "api" / "bad.py").write_text("import onboarder.core\n", encoding="utf-8")

    result = subprocess.run(
        ["lint-imports"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    assert "api" in result.stdout.lower() + result.stderr.lower()
    assert "onboarder.core" in result.stdout + result.stderr
