# Tech Market Intelligence

Evidence-backed technical job-market intelligence platform. Deterministic stored data will be source of truth for market facts; models may later extract, retrieve, and explain evidence but will not author market statistics.

## Current milestone

M0 Foundation only. Repository contains engineering contracts, typed API/provenance schemas, configuration validation, one API health endpoint, tests, and CI. Job ingestion, taxonomy, analytics, search, market UI, AI, profiles, databases, and external infrastructure are not implemented.

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

Integration, evaluation, and Compose gates are not declared in M0 because no corresponding implementation exists.

## Structure

- `apps/api/`: minimal FastAPI process scaffold
- `packages/contracts/`: typed API and provenance contracts
- `tests/`: configuration, contract, and smoke tests
- `docs/`: architecture, ADRs, configuration, and engineering policy
- `tasks/`: approved plan and milestone checklist

## Architecture and policy

- Architecture overview: `docs/architecture/overview.md`
- Engineering contract and Definition of Done: `docs/engineering/engineering-contract.md`
- Configuration and secrets: `docs/configuration/secrets.md`
- ADR-001: `docs/adr/ADR-001-modular-monolith-first.md`
- ADR-002: `docs/adr/ADR-002-postgresql-source-of-truth.md`

Development remains local-first and approximately $0. No service container, cloud resource, or paid provider is required for M0.
