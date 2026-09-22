# ADR-005: Versioned taxonomy and deterministic extraction authority

## Status

Accepted

## Date

2026-09-22

## Context

M2 normalizes roles, seniority, locations, and skills from immutable job snapshots. Taxonomy content and extraction rules can change, ambiguous text can support multiple or no labels, and later reprocessing must not erase the basis of earlier outputs. Evaluation and downstream analytics require stable identities, reproducible resource content, and evidence that resolves to exact source text.

## Decision

Publish taxonomy, normalization, and extraction resources under explicit stable versions. Compute an immutable taxonomy manifest hash from canonical content and reject different content under an existing version. Bind each derived record to its job snapshot and persist taxonomy, processor, normalization, and extraction versions. New resource or rule content receives a new version; historical outputs remain unchanged unless explicitly reprocessed into additive versioned results.

Deterministic normalization and extraction are authoritative for M2. Role, seniority, and location normalization may return ambiguous or unknown states and abstain rather than force unsupported labels. Skill extraction accepts only deterministic catalog matches and records canonical skill ID, source field, half-open Unicode code-point offsets, matched alias, method, and extractor version. Models and unreviewed candidates cannot create authoritative taxonomy entries or evidence.

Ambiguous short-alias evidence abstains from accepted job-skill facts and is persisted to a versioned candidate-review table with source span, reason, status, extractor version, and snapshot, normalization, and taxonomy references. Reviewed parent/child edges are persisted in a versioned relationship table; the initial catalog records Amazon EC2 as `PART_OF` AWS. Reviewed punctuation-sensitive aliases use precompiled boundary-aware patterns and persist the distinct `regex` method; ordinary aliases persist `alias`.

## Consequences

Published taxonomy content is reproducible and cannot drift beneath an existing version. Snapshot-bound outputs preserve historical meaning and support exact evidence inspection. Rule changes require new versions and additive reprocessing instead of silent rewrites. Abstention reduces forced false certainty; persisted candidates make unresolved evidence reviewable without promoting it to authoritative facts. Versioned relationships preserve taxonomy structure without collapsing child technologies into aliases. Exact alias matching remains vulnerable to contextual prose false positives and unsupported aliases.
