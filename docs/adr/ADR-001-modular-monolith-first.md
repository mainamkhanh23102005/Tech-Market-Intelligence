# ADR-001: Modular Monolith First

## Status

Accepted

## Context

Tech Market Intelligence has several future capabilities, but M0 has one maintainer, near-zero budget, no production workload, and no evidence that independent deployment or scaling is needed. Premature services would add network contracts, distributed failure modes, duplicated configuration, and local resource cost before product value exists.

## Decision

Use one backend codebase with explicit internal module ownership and typed in-process interfaces. API and future worker may run as separate processes from the same artifact without becoming independent services. M0 creates only minimal API and contract packages; future capability modules appear in their approved milestones.

## Alternatives

- Microservices immediately: rejected because no measured scaling, ownership, release, or isolation need exists.
- One unstructured application package: rejected because it would obscure ownership and make later extraction risky.
- Serverless functions per capability: rejected because it adds vendor/runtime constraints and weakens local reproducibility.

## Consequences

- Local setup and transactions remain simple.
- Module boundaries require discipline because process isolation does not enforce them.
- Internal calls avoid HTTP overhead.
- A future split requires an ADR and stable contract rather than moving arbitrary shared code.

## Revisit criteria

Consider extracting a module only when at least one measured need persists: independent scaling, release cadence, fault isolation, security boundary, or separate ownership. Before extraction, module must own its data writes, expose a stable typed contract, have contract tests, and document consistency and rollback behavior.
