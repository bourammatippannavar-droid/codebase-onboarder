import os
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def lint_imports_executable() -> Path:
    executable_name = "lint-imports.exe" if os.name == "nt" else "lint-imports"
    executable = Path(sys.executable).with_name(executable_name)
    if not executable.is_file():
        raise FileNotFoundError(
            f"lint-imports executable not found beside {sys.executable}: {executable}"
        )
    return executable
