# Tech Market Intelligence — Milestone Checklist

Implementation must not begin until `tasks/plan.md` receives human approval. Each task should become smaller session-sized work before execution; no task may silently add infrastructure or paid dependencies.

## M0 — Foundation

- [x] M0.1 Approve capability map, assumptions, scope, and non-goals.
  - Acceptance: unresolved assumptions recorded as decisions; no implementation starts.
  - Verify: human approval recorded.
  - Files: `tasks/plan.md`.
- [x] M0.2 Select and pin Python/Node package, formatting, lint, type-check, test, migration, and task-runner tools.
  - Acceptance: ADR records alternatives and exact commands; no unnecessary dependency selected.
  - Verify: command design reviewed before install.
  - Files: root tool configs, `docs/adr/`.
- [x] M0.3 Create minimal monorepo skeleton and engineering contract.
  - Acceptance: boundaries match plan; config/secrets policy and Definition of Done exist.
  - Verify: fresh-clone setup and quality commands work.
  - Files: root, `apps/`, `packages/`, `tests/`, `docs/`.
- [x] M0.4 Define API and provenance contracts.
  - Acceptance: versioning, pagination, error, citation, metric provenance schemas are explicit.
  - Verify: schema/contract tests pass.
  - Files: `packages/contracts/`, `docs/architecture/`.

### Checkpoint M0

- [x] PowerShell equivalents of `make format-check lint typecheck test build` succeed.
- [x] ADR-001 and ADR-002 accepted.
- [x] No feature code, cloud resource, or optional infrastructure exists.
- [x] Human approval received before M1.

## M1 — Canonical Corpus

- [x] M1.1 Define source registry, permission manifest, IDs, snapshot, and ingestion state contracts.
- [x] M1.2 Add PostgreSQL source/raw/job/snapshot schema and migration tests.
- [x] M1.3 Build validated CSV adapter over license-safe fixtures.
- [x] M1.4 Build JSON adapter using same canonical pipeline.
- [x] M1.5 Add deterministic exact deduplication, replacement, retry, and failure reporting.
- [x] M1.6 Add provenance inspection API/CLI.
- [x] M1.7 Benchmark throughput and peak memory on recorded 1k/10k fixture workloads.

Acceptance: replay creates no duplicate logical jobs; changed input creates new snapshot; every accepted job resolves to raw hash/source.

Verify: `make lint typecheck test test-integration`; import fixture twice and compare IDs/counts/hashes.

## M2 — Normalization and Skill Intelligence

- [x] M2.1 Define versioned role, seniority, location, and skill taxonomy schemas.
- [x] M2.2 Seed reviewed canonical skills, aliases, categories, and parent/child relationships.
- [x] M2.3 Build exact alias and regex extraction baseline with source spans.
  - Verified: deterministic precompiled alias/regex extraction emits distinct methods with boundary-safe source offsets.
- [x] M2.4 Build ambiguity/abstention and candidate-review path.
- [x] M2.5 Label stratified extraction/classification benchmark.
- [x] M2.6 Publish baseline precision/recall/F1 and macro-F1 report.

Acceptance: normalized outputs carry explicit versions and persisted extraction evidence carries method/version; ambiguous or unknown values can abstain or enter the persisted candidate-review path; the checked-in 24-example synthetic CC0 benchmark report is reproducible. Canonical skills include versioned alias metadata and persisted parent/child relationships. Exact alias and reviewed regex methods are distinct.

Verify: `make test test-integration test-evaluation`. Current result: 66 non-integration tests and 6 evaluation tests pass; 9 PostgreSQL integration tests are configured but skipped when `TEST_DATABASE_URL` is absent.

## M3 — Deterministic Analytics and UI

- [ ] M3.1 Define metric formulas, dimensions, denominators, coverage warnings, and versions.
- [ ] M3.2 Build immutable corpus snapshots and analytics run lifecycle.
- [ ] M3.3 Build skill distribution, role comparison, and co-occurrence aggregates from golden corpus.
- [ ] M3.4 Expose paginated, versioned market/job/evidence APIs.
- [ ] M3.5 Build minimal accessible dashboard and evidence drill-down.
- [ ] M3.6 Benchmark representative queries and inspect plans.

Acceptance: every statistic includes value, numerator, denominator, unit, dimensions, cutoff, versions, coverage warning, and evidence.

Verify: `make lint typecheck test test-integration build`; end-to-end statistic-to-source check.

## M4 — Retrieval

- [ ] M4.1 Build structured SQL search with stable keyset pagination.
- [ ] M4.2 Build PostgreSQL full-text lexical baseline.
- [ ] M4.3 Create graded retrieval benchmark and adjudication guide.
- [ ] M4.4 Define provider-neutral embedding/index contracts and evaluate local model candidates.
- [ ] M4.5 Evaluate dense and hybrid reciprocal-rank fusion.
- [ ] M4.6 Evaluate reranker only if hybrid leaves measurable headroom.
- [ ] M4.7 Record ADR selecting default and whether Qdrant is justified.

Acceptance: default search mode selected from held-out Recall@K/MRR/NDCG/latency/resource evidence.

Verify: `make test test-integration test-evaluation build`.

## M5 — Grounded Research Assistant

- [ ] M5.1 Define LLM provider ports, prompt registry, and normalized errors.
- [ ] M5.2 Implement typed read-only market/search/evidence tool contracts.
- [ ] M5.3 Implement bounded turn context, same-turn call reuse, and three-round default budget.
- [ ] M5.4 Persist conversations, messages, tool executions, citations, and prompt runs.
- [ ] M5.5 Add synthesis with fact/interpretation/general-knowledge labels and deterministic citation/number validation.
- [ ] M5.6 Add SSE status/tool/token/completion stream and reconnect behavior.
- [ ] M5.7 Add post-answer suggestions and optional redacted Langfuse adapter.
- [ ] M5.8 Publish tool and answer evaluation report.

Acceptance: frozen questions return resolvable citations and zero unsupported numeric claims; paid provider not required.

Verify: `make test test-integration test-evaluation build`; SSE reconnect and provider failure drills.

## M6 — Trends, Live Sources, Prompt Experiments

- [ ] M6.1 Implement one approved official ATS adapter with checkpoint/backoff/conditional fetch.
- [ ] M6.2 Add safe replacement/closure observation, complete-poll/grace/circuit-breaker rules, and fixed-cohort trend semantics.
- [ ] M6.3 Build skill trend API/UI with source/date/sample warnings.
- [ ] M6.4 Create prompt benchmark datasets for low-reasoning extraction/classification/routing tasks.
- [ ] M6.5 Run baseline/repeat_x2/repeat_x3/reasoning paired experiments by prompt length.
- [ ] M6.6 Record prompt repetition policy ADR from quality/token/latency evidence.

Acceptance: incompatible cohort/taxonomy/metric versions cannot be compared as one trend; partial polls cannot close jobs; repetition remains disabled unless preregistered benchmark gate wins.

Verify: offline replay of captured source fixtures and `make test-evaluation`.

## M7 — Optional Profile Intelligence

- [ ] M7.1 Approve profile privacy/threat-model ADR and authentication/ownership design.
- [ ] M7.2 Build safe blob interface and validated PDF/DOCX/TXT/MD upload boundary.
- [ ] M7.3 Build isolated text extraction and reviewable profile evidence model.
- [ ] M7.4 Build deterministic cohort comparison without generic match score.
- [ ] M7.5 Build complete deletion/reconciliation flow.
- [ ] M7.6 Evaluate parser and skill evidence quality on consented/synthetic data.

Acceptance: profile evidence remains private, reviewable, excluded from market analytics/traces, and deletable.

Verify: security, tenant isolation, parser abuse, deletion, integration, and e2e suites.

## M8 — Durable Async Processing

- [ ] M8.1 Add PostgreSQL work queue, worker process, retries, and graceful shutdown.
- [ ] M8.2 Add transactional outbox and idempotent consumer inbox.
- [ ] M8.3 Add durable progress events and SSE recovery.
- [ ] M8.4 Test crash points, duplicate delivery, poison work, and concurrent workers.
- [ ] M8.5 Benchmark throughput, lag, DB CPU/bloat, and worker scaling.
- [ ] M8.6 Decide Kafka via ADR; introduce only when plan gate is met.

Acceptance: restart loses no accepted work and duplicates no published side effects.

Verify: automated kill/restart/replay test and queue-drain check.

## M9 — Operations and Portfolio Deployment

- [ ] M9.1 Add privacy-safe Prometheus metrics and establish measured SLOs.
- [ ] M9.2 Add Grafana dashboards answering defined latency/error/lag/freshness questions.
- [ ] M9.3 Add Nginx/local Compose profiles and accepted optional stores only.
- [ ] M9.4 Add backup, restore, migration, rollback, and reconciliation runbooks.
- [ ] M9.5 Add CI quality/evaluation/security gates.
- [ ] M9.6 Produce read-only, resource-bounded free-tier demo with precomputed fallback.
- [ ] M9.7 Run clean-machine, load, failure, backup/restore, and degraded-mode verification.

Acceptance: core project runs locally near $0; public demo explains freshness/coverage; AI outage does not break deterministic analytics.

Verify: `make ci`; Compose config/smoke; restore and rollback drill.

## Standing Gate for Every Task

- [ ] Acceptance criteria tested.
- [ ] Relevant unit/integration/contract/evaluation tests pass.
- [ ] Format, lint, type-check, and build pass.
- [ ] No tests disabled, thresholds reduced, or suppressions added to obtain green.
- [ ] Data/license/security implications reviewed.
- [ ] Breaking metric, taxonomy, prompt, model, or API contract changes receive explicit version/migration; backward-compatible additive API fields keep current major version and update contract metadata.
- [ ] Significant decision captured in ADR.
- [ ] Portfolio remains demoable at milestone checkpoint.
