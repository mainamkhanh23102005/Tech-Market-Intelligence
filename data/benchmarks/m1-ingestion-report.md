# M1 ingestion benchmark

Status: blocked on 2026-09-21. Windows service discovery found no PostgreSQL service; `psql`, `pg_ctl`, `postgres`, and `docker` were unavailable. No unknown database was touched and no dependency was installed.

Environment: Windows, Python 3.12.10. Measurement starts `tracemalloc` immediately before ingestion and uses `time.perf_counter`; output reports accepted records, duplicates, failures, wall seconds, accepted records/second, and peak traced Python allocation bytes. Each workload must run once against a separate empty database upgraded to Alembic head. Database server memory and cold/warm cache behavior are outside this measurement and must not be inferred from it.

Generate deterministic workloads:

```powershell
.\.venv\Scripts\python.exe benchmarks\generate_ingestion.py 1000 data\benchmarks\ingestion-1k.json
.\.venv\Scripts\python.exe benchmarks\generate_ingestion.py 10000 data\benchmarks\ingestion-10k.json
```

Run each against an empty migrated benchmark database and record emitted JSON containing elapsed seconds, records/second, and Python peak traced memory. Results remain machine-specific and are reports, not targets.
