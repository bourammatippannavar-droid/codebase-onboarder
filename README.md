# Codebase Onboarder

A Python 3.12 command-line tool that lists classes, functions, and imports in a
Python codebase without importing or executing the analyzed files.

```powershell
uv run python -m onboarder scan <folder>
```

Run the test suite and linter with `uv run pytest` and `uv run ruff check .`.