# Codebase Onboarder

A Python 3.12 command-line tool that lists classes, functions, and imports in a
Python codebase without importing or executing the analyzed files.

```powershell
uv run python -m onboarder scan <folder>
uv run python -m onboarder deps <folder> <file>
uv run python -m onboarder used-by <folder> <file> --transitive --depth 3
uv run python -m onboarder cycles <folder>
uv run python -m onboarder find <folder> <query>
uv run python -m onboarder callers <folder> <symbol>
uv run python -m onboarder callees <folder> <symbol>
uv run python -m onboarder usages <folder> <symbol>
uv run python -m onboarder guide <folder>
```

Run checks with `uv run pytest`, `uv run ruff check .`, and
`uv run mypy --strict src`.

## Limitations

Call resolution is static and conservative. Dynamic calls, `getattr`, decorators,
and calls through unknown receivers are not resolved. The analyzer reads source
text and never imports or executes the code being analyzed.