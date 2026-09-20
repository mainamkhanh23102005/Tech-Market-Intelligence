# Engineering Contract and Definition of Done

## Runtime and tools

| Concern | Decision | Alternatives considered | Reason |
|---|---|---|---|
| Python | 3.12.x; `.python-version` pins 3.12.10 | 3.13, 3.14 | Mature FastAPI/data ecosystem and available Windows runtime; avoid newest interpreter risk |
| Python environment | stdlib `venv` + pip 25.0.1 + hashed lock | uv, Poetry, pip-tools | Zero extra bootstrap tool; Windows and CI native. Hash lock retains reproducibility |
| Packaging | `pyproject.toml` + Hatchling 1.27.0 | setuptools, Poetry | Standards-based build backend with small configuration surface |
| Formatter/linter | Ruff 0.11.12 | Black + Flake8, Pylint | One fast cross-platform dependency and one rule configuration |
| Type checker | mypy 1.16.0 strict | Pyright | Stable Python-native CI and broad library support |
| Tests | pytest 8.4.0 | unittest | Clear fixtures and future FastAPI/database test ecosystem |
| Migrations | Alembic 1.16.1 | raw SQL runner, framework-specific migration tools | Standard SQLAlchemy ecosystem choice; selected now, unused until M1 schema approval |
| Node | Node 22 LTS, baseline 22.22.0 | Node 20, Node 24 current | LTS compatibility for later Next.js; avoids current/non-LTS dependence |
| Node packages | npm 10/11 with committed `package-lock.json` when dependencies start | pnpm, Yarn | Bundled with Node and lowest Windows bootstrap cost |
| Node format/lint/types/test | Prettier, ESLint, TypeScript, Vitest when frontend starts | Biome, Jest | Planned conventional Next.js stack; not installed before frontend exists |
| Task runner | `scripts/tasks.ps1` | GNU Make, just, npm-only scripts | PowerShell is available on Windows and requires no extra global tool |
| CI | GitHub Actions, Windows runner, one M0 quality job | Linux matrix, service containers | Matches primary environment; no M0 services exist |

## Dependency policy

- `requirements.in` contains exact direct versions selected by maintainers.
- `requirements.lock` contains exact transitive versions and SHA-256 hashes and is installation authority.
- Regenerate lock in a clean Python 3.12 environment with `pip install pip-tools==7.4.1` and `pip-compile --generate-hashes --output-file requirements.lock requirements.in`; `pip-tools` is a maintenance tool, not runtime dependency.
- Install with `python -m pip install --require-hashes -r requirements.lock`.
- Commit npm lockfile when first Node dependency is introduced; CI then uses `npm ci`.
- Dependency updates are deliberate, one ecosystem at a time, with release-note/security review and all gates passing. No floating production ranges.

## Configuration and secrets

- Environment variables configure deployment-specific values.
- `.env.example` contains non-secret placeholders/defaults only; `.env*` files remain ignored except example.
- `local`, `test`, and `production` are explicit environments.
- Optional future provider keys stay unset until feature use.
- Configuration validates at startup and never prints secret values.
- Full policy: `docs/configuration/secrets.md`.

## Testing layers

- Unit: pure configuration and domain behavior, no network or services.
- Contract: API/schema compatibility and in-process application smoke tests.
- Integration: multiple modules or PostgreSQL; starts in milestone that introduces those dependencies.
- Evaluation: labeled quality benchmarks; starts with relevant extraction/retrieval milestone.
- End-to-end: critical user workflows only after UI exists.

M0 requires unit and contract tests only. Empty integration/evaluation commands are forbidden.

## Migration policy

- Alembic is selected but no migration environment or database schema exists in M0.
- M1 migrations must be ordered, immutable after shared use, and tested forward from empty database.
- Schema changes must be backward-compatible during deployment where old and new code can overlap.
- Destructive changes require expand/migrate/contract sequence, backup/restore consideration, and ADR when significant.

## Breaking changes

- Public API uses `/api/v1`.
- Additive optional fields are preferred.
- Removing fields, changing meaning/type, or changing error/pagination semantics requires migration plan and major version review.
- Contract tests change with approved contract, never merely to make CI green.
- Metric, taxonomy, prompt, and model changes carry their own semantic versions as later milestones define them.

## ADR process

1. Create sequential `docs/adr/ADR-NNN-title.md`.
2. Use Status, Context, Decision, Alternatives, Consequences, and Revisit criteria.
3. Begin Proposed; project owner marks Accepted after review.
4. Never delete accepted history. A replacement ADR marks predecessor Superseded.

## Definition of Done

A task is done only when:

- Acceptance criteria are demonstrably met.
- Scope stays within approved milestone.
- Formatting, lint, strict type checking, tests, and build pass through root runner.
- New behavior has appropriate tests; no test is skipped or weakened.
- Boundary inputs and errors follow contracts.
- Secrets and sensitive data are absent from source, output, logs, and fixtures.
- Relevant docs and ADRs explain changed decisions.
- Dependency and lock changes are intentional and reproducible.
- `git diff --check` passes when repository has Git metadata.
- Reviewer can run documented setup on Windows PowerShell.

## Quality commands

`format-check`, `lint`, `typecheck`, `test`, and `build` perform real work. `ci` runs all five. Integration, evaluation, and Compose checks will be added only when real artifacts exist.
