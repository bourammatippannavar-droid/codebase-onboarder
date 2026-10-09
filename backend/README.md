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

Run these commands from the `backend/` directory.

Run checks from `backend/` with `uv run pytest`, `uv run ruff check .`,
`uv run mypy --strict src`, and `uv run lint-imports`.

## Local PostgreSQL

Install PostgreSQL 16 locally and make sure the server is running. From `psql`
as a PostgreSQL administrator, create a role and separate application and test
databases:

```sql
CREATE ROLE onboarder LOGIN PASSWORD 'choose-a-local-password';
CREATE DATABASE onboarder OWNER onboarder;
CREATE ROLE onboarder_test LOGIN PASSWORD 'choose-a-different-local-password';
CREATE DATABASE onboarder_test OWNER onboarder_test;
```

From the repository root, copy `.env.example` to `.env` and replace its
placeholders with the local connection URLs and an absolute `ANALYSIS_ROOT`
directory. Settings load this root `.env` file regardless of the working
directory. Keep `.env` local; it is ignored by Git. Use `TEST_DATABASE_URL`
only for the dedicated test database.

Apply the schema from `backend/` with `uv run alembic upgrade head`. The
database-backed tests use `TEST_DATABASE_URL`, and skip with a clear reason
only when that variable is unset or its PostgreSQL server is unreachable.

## Limitations

Call resolution is static and conservative. Dynamic calls, `getattr`, decorators,
and calls through unknown receivers are not resolved. The analyzer reads source
text and never imports or executes the code being analyzed.