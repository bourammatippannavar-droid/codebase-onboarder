# Codebase Onboarder

A Python 3.12 command-line tool that lists classes, functions, and imports in a
Python codebase without importing or executing the analyzed files.

```powershell
uv run python -m onboarder scan <folder>
uv run python -m onboarder deps <folder> <file>
uv run python -m onboarder used-by <folder> <file> --transitive --depth 3
uv run python -m onboarder cycles <folder>
```

Run checks with `uv run pytest`, `uv run ruff check .`, and
`uv run mypy --strict src`.