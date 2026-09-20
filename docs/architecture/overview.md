# Architecture Overview

## M0 shape

```text
PowerShell quality runner
        |
        +-- FastAPI health-only scaffold
        +-- typed API/provenance contract package
        +-- unit/contract smoke tests
```

No database, frontend, worker, queue, vector store, cache, object store, model provider, or monitoring service runs in M0.

## Capability boundaries

Approved boundaries remain `platform-foundation`, `market-corpus`, `skill-intelligence`, `market-analytics`, `market-experience`, `retrieval`, `research-assistant`, `profile-intelligence`, `event-processing`, and `operations` in `tasks/plan.md`. M0 implements only `platform-foundation` and cross-cutting contracts needed to prevent later interface drift.

Future backend capabilities remain modules in one Python codebase until ADR-001 extraction criteria are met. PostgreSQL becomes runtime authority in M1, not M0.

## API conventions

- Prefix product endpoints with `/api/v1`.
- System endpoints such as `/health` remain outside versioned product API.
- Validate external input at boundary.
- Return one error shape:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request is invalid",
    "details": {},
    "request_id": "request-id"
  }
}
```

- Use opaque cursor/keyset pagination:

```json
{
  "next_cursor": "opaque-or-null",
  "has_more": false
}
```

- List payload shape and cursor encoding wait for M1 data model.
- Additive optional fields may retain `/api/v1`; removals or semantic/type changes require migration and a new major API version.

## Provenance contract

Future market facts carry:

- corpus snapshot ID
- metric version
- taxonomy version
- numerator and denominator
- unit
- dimensions
- source cutoff timestamp
- evidence references
- optional coverage warning

Contract types exist without analytics behavior. Evidence references identify stored evidence and job snapshot; source URL remains optional because display permission may vary.

## Logging and errors

Use structured event records with timestamp, severity, event name, request/correlation ID, component, and bounded non-sensitive fields. Never log secrets, profile text, raw documents, authorization headers, or provider payloads. Metrics and logging adapters wait for measured runtime need.

Errors crossing API boundaries use stable machine-readable codes and safe messages. Internal details remain in redacted logs. Configuration errors identify missing/invalid field names without values.
