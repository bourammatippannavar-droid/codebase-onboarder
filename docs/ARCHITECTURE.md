# Architecture

Codebase Onboarder separates its Python analysis pipeline, application services, HTTP API, and persistence. The browser frontend and CLI are entry points; the API and CLI delegate work to services, while services use repository protocols rather than depending on the persistence implementation.

## Layers and responsibilities

| Layer | Responsibility |
| --- | --- |
| React frontend | Repository management, overview, graph, explorer, guide, and API-backed search UI. |
| FastAPI API | Validates requests, exposes analysis and query endpoints, assigns request IDs, and translates errors into problem responses. |
| Services | Apply path and request rules, coordinate analysis and queries, build response views, and depend on repository protocols. |
| Core analysis | Scans Python files, parses syntax trees, resolves imports and calls, constructs dependency graphs, detects cycles, and generates guides. |
| Database layer | Implements repository protocols with SQLAlchemy and PostgreSQL persistence. |
| PostgreSQL | Stores repositories and their analyzed files, symbols, and relationship edges. |

The CLI also invokes analysis/query services and core commands. Application bootstrap wires services to the database implementation. Import-linter checks four contracts: core excludes frameworks and outer layers; services exclude persistence implementations and frameworks; the database layer excludes FastAPI; and the API avoids direct core/database implementation dependencies. Composition and configured integration exceptions are explicitly listed in `.importlinter`.

## Request flow: add a repository to ready

1. The browser submits the local directory path and repository name to `POST /api/v1/repositories`.
2. The service validates that the path exists under the configured analysis root. Canonical path resolution keeps symlinks from escaping that root.
3. The API creates a `pending` repository record and submits work to the application’s analysis executor.
4. The worker marks it `running`, scans Python files, parses symbols/imports, resolves project imports and calls, and builds edge inputs and summary statistics.
5. The repository implementation persists files, symbols, edges, and statistics transactionally, then sets the repository status to `ready`. On analysis failure it stores a sanitized failure status/message instead.
6. The frontend polls repository status and enables the explorer and other repository views after readiness.

## Database tables

- `repositories`: local path, display name, status, summary statistics, sanitized failure information, and lifecycle timestamps.
- `files`: analyzed relative paths, line counts, entry-point indicators, parse status, and owning repository.
- `symbols`: classes, functions, and methods with qualified names and source line ranges.
- `edges`: import and call relationships, optional source/target file and symbol references, confidence, origin, and line number.
- `alembic_version`: schema migration bookkeeping maintained by Alembic.

Foreign keys connect analysis rows to repositories, files, and symbols; deleting a repository cascades to its analysis rows.
