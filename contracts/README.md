# API contracts (MVP-0)

## Source of truth

For **MVP-0**, the **live OpenAPI document** exposed by the running FastAPI app is the **authoritative API contract**:

- **`GET /openapi.json`** — same schema FastAPI uses for interactive docs (`/docs`).

Do not treat hand-maintained YAML/JSON in this folder as the primary spec unless it is explicitly generated from or verified against that endpoint.

### What comes later

- **Typed clients** (e.g. OpenAPI Generator, `openapi-typescript`, or similar) can be generated from `openapi.json`.
- **Pinned snapshots** of the schema (checked in or produced in CI) can be added when you want diffable contract reviews or client codegen in the pipeline. MVP-0 does not require that yet.

## Optional local snapshot

You can save a copy of the contract next to this README for local diffing or tooling while the API is running (default dev port **8000**):

```bash
curl -sS "http://127.0.0.1:8000/openapi.json" -o contracts/openapi.json
```

On Windows PowerShell you can use the same URL with `Invoke-WebRequest` if you prefer:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/openapi.json" -OutFile "contracts/openapi.json"
```

### Git and `contracts/openapi.json`

**`contracts/openapi.json` is optional** and is **ignored by Git** (see root `.gitignore`). That keeps snapshots **local-only**: useful for ad-hoc diffs without committing generated files or fighting merge noise.

If you later want a **committed** pinned contract for CI or codegen, remove the ignore entry (or use a different path like `contracts/snapshots/openapi.json`) and document the new convention in this file.
