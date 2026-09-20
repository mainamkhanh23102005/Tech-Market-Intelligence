# M0 Approval Record

Status: Approved for M0 implementation
Date: 2026-09-20
Source: `tasks/plan.md` and `tasks/todo.md`

Tech Market Intelligence is an evidence-backed technical job-market and career-intelligence platform. Primary differentiation is reproducible deterministic analytics with traceable job evidence rather than unsupported advice or opaque profile-match scores.

Approved constraints:

- Local-first, open-source-first, and approximately $0 development.
- Modular monolith before service extraction.
- PostgreSQL as initial operational and analytics source of truth.
- Market counts, percentages, rankings, and trends come from stored data and deterministic metric definitions.
- LLMs may later extract, classify, retrieve, and explain; they are not authoritative sources of market statistics.
- Profile/resume analysis remains optional and secondary.

M0 excludes ingestion, taxonomy, analytics, search, market UI, AI/model calls, profiles, external APIs, cloud resources, and optional infrastructure. Complete scope, assumptions, capability map, and non-goals remain in `tasks/plan.md`.
