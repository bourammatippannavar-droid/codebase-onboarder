import os
from pathlib import Path

SKIPPED_DIRECTORIES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
}
MAX_FILE_SIZE = 1_048_576


def find_python_files(root: Path) -> list[Path]:
    """Return Python files under root, excluding generated, large, or linked paths."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        return []

    python_files = []
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [
            name
            for name in directories
            if name not in SKIPPED_DIRECTORIES
            and not (current_path / name).is_symlink()
        ]

        for name in filenames:
            path = current_path / name
            if path.suffix != ".py" or path.is_symlink():
                continue
            try:
                if path.stat(follow_symlinks=False).st_size > MAX_FILE_SIZE:
                    continue
            except OSError:
                continue
            python_files.append(path)

    return sorted(python_files, key=lambda path: path.as_posix())