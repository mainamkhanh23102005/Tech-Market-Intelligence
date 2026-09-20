# ADR-002: PostgreSQL as Initial Source of Truth

## Status

Accepted

## Context

Future corpus, provenance, taxonomy, analytics snapshots, conversations, and processing state are relational and require transactional consistency. Project must run locally at near-zero cost. M0 defines this authority but creates no database schema or running PostgreSQL service; runtime database work begins in M1.

## Decision

Use PostgreSQL as initial operational authority and initial deterministic analytics authority. Raw/source metadata, canonical records, versions, metric inputs, and published snapshots will remain traceable through PostgreSQL records or content-addressed artifacts referenced by them.

Qdrant, Kafka, Redis, MinIO, and separate analytical stores are deferred until approved measurement gates. Derived indexes, caches, and event transports must be rebuildable from PostgreSQL and retained source artifacts. PostgreSQL is not replaced as authority merely because a specialized read path is added.

## Alternatives

- SQLite: useful for embedded prototypes but rejected as project authority because planned concurrent API/worker behavior and PostgreSQL-specific search/analytics need one reproducible target.
- Document database: rejected because core identities, many-to-many skills, temporal snapshots, and provenance are relational.
- Qdrant as primary store: rejected because vector retrieval is derived and cannot govern relational facts or deterministic metrics.
- Kafka as system of record: rejected because no event-stream scale/replay need exists and queryable operational authority is still required.
- Managed cloud database: rejected as mandatory architecture because it violates local-first and near-zero-cost constraints.

## Consequences

- M1 must define migrations, backup expectations, and transactional ownership before adding tables.
- Initial analytics can use SQL and materialized data without a separate warehouse.
- Specialized systems introduce synchronization, tombstone, rebuild, and reconciliation duties.
- Local development eventually needs one PostgreSQL service, but M0 CI needs none.

## Revisit criteria

Add a specialized system only after its plan gate is measured and accepted by ADR. Any derived system must record source IDs and versions, define rebuild and deletion behavior, and demonstrate that PostgreSQL/source artifacts can recover authoritative state.
