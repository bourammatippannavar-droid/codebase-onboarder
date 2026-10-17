# Codebase Onboarder

[![CI (push)](https://github.com/bourammatippannavar-droid/codebase-onboarder/actions/workflows/ci.yml/badge.svg?branch=main&event=push)](https://github.com/bourammatippannavar-droid/codebase-onboarder/actions/workflows/ci.yml)
[![CI (pull request)](https://github.com/bourammatippannavar-droid/codebase-onboarder/actions/workflows/ci.yml/badge.svg?branch=main&event=pull_request)](https://github.com/bourammatippannavar-droid/codebase-onboarder/actions/workflows/ci.yml)

Codebase Onboarder maps how a Python codebase fits together—its imports, calls, and circular dependencies—and generates an onboarding guide.

It is a Python-only analyzer. Continuous integration runs on GitHub Actions.

## Why I built it

New developers can spend days finding the right place to start in an unfamiliar codebase. File lists alone do not explain how modules connect or which paths through the code are useful. I built this tool to turn static source analysis into a navigable map and a practical reading order. It reads source without running the project being analyzed.

## Screenshots

No screenshots are available in this checkout.

## Features

- Analyzes Python source only, finding classes, functions, methods, and imports without executing it.
- Resolves project imports and statically detected calls, and reports circular imports.
- Builds an interactive dependency graph and a file-and-symbol explorer with source, outline, and relationship views.
- Generates an onboarding guide with entry points, a suggested reading order, import hotspots, and analysis-quality information.
- Provides a FastAPI service, a React web interface, and a command-line interface for local folders.

## How it works

1. **Scan** Python files in the selected local folder.
2. **Parse** source into symbols and import references using Python’s syntax tree.
3. **Resolve** project imports and statically recognizable calls.
4. **Build** relationship edges, dependency graphs, cycles, and an onboarding guide.

An **exact** edge points to a statically resolved target; **inferred** marks a likely target inferred from available static information. **Unresolved** records a call for which the analyzer cannot identify a target; external standard-library and third-party references are classified separately.

## Architecture

```mermaid
flowchart LR
    Browser --> React["React frontend"]
    React --> API["FastAPI API"]
    CLI["CLI"] --> Services
    API --> Services
    Services --> Core["Core analysis"]
    Services --> DB["Database layer"]
    DB --> PostgreSQL
```

Import-linter enforces the boundaries: core analysis avoids outer frameworks and the CLI; services avoid the database implementation and web frameworks; the database layer avoids FastAPI; and the API does not directly depend on core or database implementation modules. The composition/bootstrap and explicitly configured integration points are kept at the application boundary.

## Security

- Analyzed Python code is parsed as text and is never imported or executed.
- Configured analysis roots are enforced, with resolved paths checked to prevent symlink escapes.
- Files larger than the 1 MiB analysis limit are excluded.
- Unexpected failures are logged by type and returned without leaking tracebacks or sensitive paths.
- API errors use `application/problem+json` and carry a request ID.

## Quick start

Install PostgreSQL 16 for Windows and make sure its `bin` directory is available. In a fresh PowerShell session, start its service and create separate application and test databases (replace the example passwords with your own local values):

```powershell
Start-Service postgresql-x64-16
$env:Path = "$env:ProgramFiles\PostgreSQL\16\bin;$env:Path"
psql -h localhost -U postgres -d postgres -c "CREATE ROLE onboarder LOGIN PASSWORD 'choose-a-local-password';"
psql -h localhost -U postgres -d postgres -c "CREATE DATABASE onboarder OWNER onboarder;"
psql -h localhost -U postgres -d postgres -c "CREATE ROLE onboarder_test LOGIN PASSWORD 'choose-a-different-local-password';"
psql -h localhost -U postgres -d postgres -c "CREATE DATABASE onboarder_test OWNER onboarder_test;"
```

From the repository root, copy the environment template and edit it with the database URLs and an absolute analysis root:

```powershell
Copy-Item .env.example .env
notepad .env
```

Use these connection URLs with the passwords chosen above. If a password contains URL-reserved characters, percent-encode them; set `ANALYSIS_ROOT` to a directory that will contain the local projects you analyze:

```text
DATABASE_URL=postgresql+psycopg://onboarder:choose-a-local-password@localhost:5432/onboarder
TEST_DATABASE_URL=postgresql+psycopg://onboarder_test:choose-a-different-local-password@localhost:5432/onboarder_test
ANALYSIS_ROOT=C:\code\analysis
```

Create the configured root if it does not exist:

```powershell
New-Item -ItemType Directory -Force C:\code\analysis | Out-Null
```

Prepare the backend and database schema:

```powershell
Set-Location .\backend
uv sync --frozen
uv run alembic upgrade head
```

In that PowerShell window, start the API:

```powershell
uv run uvicorn onboarder.api.app:app --reload
```

In a second PowerShell window opened at the repository root, start the frontend:

```powershell
Set-Location .\frontend
npm ci
npm run dev
```

After creating a Python project directory under your configured `ANALYSIS_ROOT`, add it through the local API:

```powershell
$body = @{
    path = 'C:\code\analysis\my-python-project'
    name = 'my-python-project'
} | ConvertTo-Json
Invoke-RestMethod -Method Post `
    -Uri 'http://127.0.0.1:8000/api/v1/repositories' `
    -ContentType 'application/json' `
    -Body $body
```

The request returns while analysis is queued; the repository becomes available when its status is `ready`.

## Testing

The latest local runs passed **76 backend tests** with **91% total coverage** and **34 frontend tests**. These are test coverage figures, not analyzer accuracy metrics. GitHub Actions runs the backend and frontend gates shown below; its production dependency audit is informational and does not fail CI.

```powershell
# backend/
uv run ruff check .
uv run mypy --strict src
uv run lint-imports
uv run pytest --cov=onboarder --cov-report=term --cov-report=xml:coverage.xml

# frontend/
npm run lint
npm run typecheck
npm test
npm run build
npm run check:api
```

CI also runs `npm audit --omit=dev` as a non-blocking informational check.

Database-backed tests use `TEST_DATABASE_URL`. For local PostgreSQL setup and all available CLI commands, see [backend/README.md](backend/README.md).

## The tool analyzing its own code

On **2026-10-17** (commit **`3faaf42`**), the CLI analyzed `backend/src/onboarder`: **27 Python files**, **301 symbols**, and **no circular imports**. Its guide reported a **94.3% call-resolution rate**: 247 resolved call edges out of 262 stored call edges.

Reproduce the guide and cycle check from `backend/`:

```powershell
uv run python -m onboarder guide src\onboarder
uv run python -m onboarder cycles src\onboarder
```

The guide also reported 15 stored unresolved calls and 1,106 calls not stored (382 unknown-receiver, 391 external-package, and 333 builtin calls).

## Limitations

- Python only; JavaScript and TypeScript are not analyzed.
- Dynamic dispatch, `getattr`, and decorator effects are not resolved.
- Calls through unknown receivers are not stored as relationship edges.
- The tool analyzes local folders only; it does not clone GitHub URLs or import private repositories.

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md) for details.

## What I would do next

- Add JavaScript and TypeScript support using Tree-sitter.
- Support importing a repository from a GitHub URL.
- Add incremental re-analysis when files change.
- Publish a hosted, read-only demo.

## Project docs

- [Architecture](docs/ARCHITECTURE.md)
- [Limitations](docs/LIMITATIONS.md)
- [MIT License](LICENSE)
