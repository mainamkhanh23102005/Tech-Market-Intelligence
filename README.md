# Tech Market Intelligence

Evidence-backed technical job-market intelligence platform. Deterministic stored data will be source of truth for market facts; models may later extract, retrieve, and explain evidence but will not author market statistics.

## Current milestone

M1 Canonical Corpus. Repository contains bounded CSV/JSON ingestion, deterministic identities and snapshots, PostgreSQL schema/migrations, duplicate and failure reporting, historical provenance CLI, tests, and benchmark tooling. Taxonomy, analytics, search, market UI, AI, profiles, and live source adapters are not implemented.

## Supported toolchain

- Python 3.12.x; pinned local reference: 3.12.10
- Node.js 22 LTS; pinned baseline: 22.22.0
- npm 10 or 11; no Node dependencies or frontend scaffold in M0
- PowerShell 5.1+ task runner

## Setup on Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip==25.0.1
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
Copy-Item .env.example .env
```

`requirements.lock` is authoritative for repeatable installs. `requirements.in` documents direct dependencies used to regenerate it according to `docs/engineering/engineering-contract.md`.

## Quality commands

```powershell
.\scripts\tasks.ps1 format
.\scripts\tasks.ps1 format-check
.\scripts\tasks.ps1 lint
.\scripts\tasks.ps1 typecheck
.\scripts\tasks.ps1 test
.\scripts\tasks.ps1 build
.\scripts\tasks.ps1 ci
```

`test` and `test-unit` exclude PostgreSQL integration tests. Set `TEST_DATABASE_URL` to an isolated migrated test database before `test-integration`; set `DATABASE_URL` before `migrate` or CLI use. `BENCHMARK_DATABASE_URL` must identify a separate empty migrated benchmark database.

```powershell
.\scripts\tasks.ps1 test-unit
.\scripts\tasks.ps1 test-integration
.\scripts\tasks.ps1 migrate
.\.venv\Scripts\tech-market-ingestion.exe import data\fixtures\jobs.csv --manifest data\manifests\synthetic-jobs.json
.\.venv\Scripts\tech-market-ingestion.exe provenance --job-id <uuid>
.\.venv\Scripts\tech-market-ingestion.exe provenance --snapshot-id <uuid>
```

## Structure

- `apps/api/`: minimal FastAPI process scaffold
- `packages/backend/`: M1 ingestion, persistence, and provenance implementation
- `packages/contracts/`: typed API and provenance contracts
- `migrations/`: explicit frozen PostgreSQL Alembic operations
- `benchmarks/`: deterministic workload generator and ingestion measurement runner
- `tests/`: contract, unit, and isolated PostgreSQL integration tests
- `docs/`: architecture, ADRs, configuration, and engineering policy
- `tasks/`: approved plan and milestone checklist

## Architecture and policy

- Architecture overview: `docs/architecture/overview.md`
- Engineering contract and Definition of Done: `docs/engineering/engineering-contract.md`
- Configuration and secrets: `docs/configuration/secrets.md`
- ADR-001: `docs/adr/ADR-001-modular-monolith-first.md`
- ADR-002: `docs/adr/ADR-002-postgresql-source-of-truth.md`

Development remains local-first and approximately $0. M1 PostgreSQL can use an existing native service or optional Compose dependency; commands never create or select an unknown database implicitly.
