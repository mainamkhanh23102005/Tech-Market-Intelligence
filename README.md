# Tech Market Intelligence

Evidence-backed technical job-market intelligence platform. Deterministic stored data will be source of truth for market facts; models may later extract, retrieve, and explain evidence but will not author market statistics.

## Current milestone

M3 Deterministic Analytics and First Useful UI is implemented in this working tree. Repository now includes versioned metric definitions, immutable exact-membership corpus snapshots, analytics-run and statistic storage, deterministic skill/role/location/co-occurrence calculations, versioned paginated FastAPI contracts, and a minimal accessible Next.js evidence drill-down. M4.1 structured search and the M4.2 PostgreSQL lexical baseline are implemented; retrieval benchmarks, dense/hybrid retrieval, reranking, AI, profiles, and live source adapters remain unimplemented.

## Job search baseline

`GET /api/v1/jobs/search` requires `snapshot` (corpus UUID) and `analytics_run_id` (compatible successful run UUID). Omitted `mode` and `mode=structured` preserve M4.1 title/company substring search. `mode=lexical` is opt-in and requires a nonblank `query`; unsupported modes and invalid inputs use structured 422 error envelopes. M4.7 will select the default retrieval mode from evidence, not this baseline.

Lexical retrieval runs entirely in PostgreSQL with explicit `simple` text-search configuration and `websearch_to_tsquery`. Unquoted words use AND, uppercase `OR` combines alternatives, `-` excludes terms, and quoted words require adjacent positions. Unmatched quotes are tolerated by the parser; punctuation-only queries return no matches. `simple` lowercases without stemming: `running` and `run` differ. Tests pin actual PostgreSQL 16 behavior for Python, PostgreSQL, AWS, Node.js, C++, and .NET. Punctuation is not preserved faithfully: C++ becomes `c`, .NET becomes `net`, and Node.js retains its dotted lexeme. Canonical skills contribute their frozen keys (for example `cpp`), not expanded aliases; this is not semantic or taxonomy-aware query rewriting. Concatenated field vectors can allow phrases across field boundaries; phrases are not guaranteed field-local.

The query-time document weights title A (1.0), frozen canonical skills B (0.4), company C (0.2), and description D (0.1). Skills come from the selected `AnalyticsRunMember` JSONB array using `jsonb_to_tsvector`, never live extraction records. `ts_rank_cd` uses default weights and normalization 0. Ordering is rank descending, observed time descending, snapshot UUID ascending. Keyset cursors bind corpus/run/query/filters/page size and lexical mode/version; the anchor must match the same database-filtered scope, and its rank is recomputed in SQL to avoid floating-point cursor rounding. Existing structured cursors remain compatible.

Role, seniority, location, all requested skills, and inclusive observed-time bounds execute inside retrieval SQL. Lexical membership also joins the requested corpus's exact snapshots. Evidence URLs remain corpus-pinned; descriptions participate in matching but never appear in result summaries. No schema migration or GIN index is added: the document spans immutable source snapshots and run-specific frozen skills, so an indexed materialization would require backfill/publication lifecycle work. Query-time FTS is the correctness baseline, not a claim of indexed production throughput. Later performance evidence can justify a rebuildable index without changing frozen membership.

## Supported toolchain

- Python 3.12.x; pinned local reference: 3.12.10
- Node.js 22 LTS; pinned baseline: 22.22.0
- npm 10 or 11; exact frontend dependencies and `package-lock.json`
- PowerShell 5.1+ task runner

## Setup on Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip==25.0.1
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
Copy-Item .env.example .env
npm ci
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
.\scripts\tasks.ps1 web-test
.\scripts\tasks.ps1 web-build
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
.\.venv\Scripts\tech-market-analytics.exe --cutoff 2026-09-20T00:00:00Z
.\.venv\Scripts\python.exe benchmarks\generate_m3_demo.py --database-url $env:BENCHMARK_DATABASE_URL --iterations 30 --json-output data\benchmarks\analytics\m3-engineering-report.json --markdown-output data\benchmarks\analytics\m3-engineering-report.md
```

## Structure

- `apps/api/`: FastAPI health plus versioned M3 market/job/evidence read API
- `apps/web/`: minimal Next.js market dashboard and evidence drill-down
- `packages/backend/`: M1 corpus, M2 normalization/extraction, and M3 deterministic analytics implementation
- `packages/contracts/`: typed API, market-statistic, pagination, and provenance contracts
- `migrations/`: explicit frozen PostgreSQL Alembic operations
- `benchmarks/`: deterministic ingestion and M3 analytics/report benchmark runners
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

Development remains local-first and approximately $0. PostgreSQL can use an existing native service or optional Compose dependency; commands never create or select an unknown database implicitly. M3 adds Alembic revision `0003_m3_analytics`; the checked-in synthetic engineering report records a successful empty-to-head migration, six-job publication, exact corpus-scoped evidence drill-down, and representative query plans/latencies. Current M3 host verification passed 88 Python non-integration tests (including 6 evaluation tests), 23 isolated PostgreSQL integration tests, and 19 Vitest UI tests, plus Ruff format/lint, strict mypy, Git whitespace validation, TypeScript, ESLint, Python wheel, and a production Next.js build. Fresh isolated empty-to-head and seeded M2-to-M3 databases reached `0003_m3_analytics` while preserving representative M2 rows; the checked-in M3 engineering report was regenerated from that publication.
