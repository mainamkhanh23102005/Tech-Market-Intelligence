# M3 Golden Analytics Report

- Fixture: `golden-corpus.json`
- Version: `m3-golden-1.0.0`
- License: CC0-1.0
- Cutoff: `2026-09-20T00:00:00Z`
- Selected exact membership: `snap-a`, `snap-b`, `snap-z`
- Distinct logical jobs: 3
- Python prevalence: 3 / 3 = 1
- PostgreSQL prevalence: 2 / 3 = 0.6666666667
- Python/PostgreSQL co-occurrence: 2 / 3 = 0.6666666667
- Unknown role: 1 / 3
- Unknown location and work arrangement: 1 / 3

Selection uses latest `observed_at <= cutoff` per logical job and greatest snapshot ID as deterministic tie break. Duplicate skills within one job count once. Future observations and superseded historical snapshots do not count. Only accepted M2 evidence is eligible in persisted analytics.
