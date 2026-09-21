# ADR-004: Permission-gated bounded file ingestion

## Status

Accepted

## Date

2026-09-21

## Context

M1 needs license-safe reproducible fixtures without broad scraping or unbounded input handling. Every accepted record must retain source permission and raw evidence.

## Decision

Accept local CSV and JSON only when a validated permission manifest has `approved` status. Persist versioned manifest content and review timestamp. Apply configurable file, record-count, and per-record byte bounds before persistence. Store canonical validated payload and SHA-256 hash; retain terminal validation failures and retryable infrastructure failures separately. Live network adapters remain outside M1.

## Consequences

Unapproved sources fail before run creation. Fixtures and imports remain bounded and reproducible. JSON currently loads one bounded file into memory; benchmark peak memory makes that cost visible. Source-policy changes create new permission rows rather than rewriting prior evidence.
