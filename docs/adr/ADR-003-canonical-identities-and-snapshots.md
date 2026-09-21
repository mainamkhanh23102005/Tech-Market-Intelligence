# ADR-003: Deterministic identities and temporal snapshots

## Status

Accepted

## Date

2026-09-21

## Context

M1 imports must replay safely, preserve changed postings, and resolve every accepted snapshot to source evidence. Source records may expose stable posting IDs or only canonical URLs. Corrections must not erase historical evidence.

## Decision

Derive source, job, raw-record, and snapshot UUIDs with UUIDv5. Job identity uses source namespace plus source posting ID, falling back to canonical URL. Raw identity uses source plus SHA-256 canonical JSON hash. Snapshot identity adds job, raw hash, and processor version. Replays record processing attempts and report duplicates without adding logical jobs or snapshots. Changed content creates a new immutable snapshot. Provenance inspection accepts exactly one job or snapshot ID; job lookup returns latest observed snapshot while snapshot lookup returns historical evidence.

## Consequences

Replays are idempotent at corpus level while remaining auditable by ingestion run. Corrections are additive. Identity-policy changes require a new processor/identity version and migration rather than silent rewriting.
