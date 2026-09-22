# Tech Market Intelligence

Evidence-backed technical job-market intelligence platform. Deterministic stored data will be source of truth for market facts; models may later extract, retrieve, and explain evidence but will not author market statistics.

## Current milestone

M2 Normalization and Skill Intelligence. Repository contains M1 corpus ingestion plus versioned role, seniority, location, and skill normalization; deterministic precompiled alias/regex extraction with source offsets; ambiguity/abstention and persisted candidate-review evidence; versioned parent/child taxonomy relationships; snapshot-bound persisted outputs; and a reproducible 24-example synthetic CC0 evaluation. Analytics, search, market UI, AI, profiles, and live source adapters are not implemented.

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
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
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
.\scripts\tasks.ps1 test-evaluation
.\scripts\tasks.ps1 evaluation
.\.venv\Scripts\tech-market-evaluation.exe
.\.venv\Scripts\python.exe -m tech_market_backend.taxonomy.evaluation_cli
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
- `packages/backend/`: M1 corpus plus M2 normalization, taxonomy, extraction, persistence, and evaluation implementation
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
- ADR-003: `docs/adr/ADR-003-canonical-identities-and-snapshots.md`
- ADR-004: `docs/adr/ADR-004-source-permission-and-retention.md`
- ADR-005: `docs/adr/ADR-005-taxonomy-versioning-and-extraction-authority.md`

Development remains local-first and approximately $0. PostgreSQL can use an existing native service or optional Compose dependency; commands never create or select an unknown database implicitly. Canonical verification commands are `.\scripts\tasks.ps1 test`, `.\scripts\tasks.ps1 test-integration`, and `.\scripts\tasks.ps1 test-evaluation`; current verified totals are 66 non-integration tests, 9 PostgreSQL integration tests, and 6 evaluation-suite tests. The full integration suite ran against the isolated `tech_market_test` database, and a fresh migration reached Alembic head `0002_m2_normalization`.
