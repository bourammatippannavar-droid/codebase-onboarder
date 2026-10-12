# Codebase Onboarder

The application and its commands live in [backend](backend/README.md). Run project commands from `backend/`.

For local PostgreSQL 16 provisioning, credentials, and migration setup, see
[the backend README](backend/README.md#local-postgresql). Copy the root
[`.env.example`](.env.example) to `.env`; keep the local credentials out of Git.

## Run the frontend

Run the backend API from `backend/` and the frontend from `frontend/`:

```powershell
npm install
npm run dev
```

The Vite development server proxies `/api` requests to
`http://127.0.0.1:8000`. Frontend checks from `frontend/`:
`npm run lint`, `npm run typecheck`, `npm test`, `npm run build`,
`npm run check:api`, and `npm audit --omit=dev`.
Regenerate OpenAPI types from `backend/openapi.json` with `npm run gen:api`;
verify the committed output with `npm run check:api`.