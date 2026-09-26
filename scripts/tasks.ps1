param(
    [Parameter(Position = 0)]
    [ValidateSet("format", "format-check", "lint", "typecheck", "test", "test-unit", "test-integration", "test-evaluation", "evaluation", "build", "migrate", "web-test", "web-build", "benchmark-analytics", "ci")]
    [string]$Task = "ci"
)

$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing .venv. Run: py -3.12 -m venv .venv"
}

function Invoke-Step([string]$Name, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

switch ($Task) {
    "format" { Invoke-Step "format" { & $python -m ruff format . } }
    "format-check" { Invoke-Step "format-check" { & $python -m ruff format --check . } }
    "lint" {
        Invoke-Step "python lint" { & $python -m ruff check . }
        Invoke-Step "web lint" { npm.cmd run web:lint }
    }
    "typecheck" {
        Invoke-Step "python typecheck" { & $python -m mypy }
        Invoke-Step "web typecheck" { npm.cmd run web:typecheck }
    }
    "test" { Invoke-Step "test" { & $python -m pytest -m "not integration" } }
    "test-unit" { Invoke-Step "test-unit" { & $python -m pytest -m "not integration" } }
    "test-integration" { Invoke-Step "test-integration" { & $python -m pytest -m integration } }
    "test-evaluation" { Invoke-Step "test-evaluation" { & $python -m pytest tests/evaluation } }
    "evaluation" { Invoke-Step "evaluation" { & $python -m tech_market_backend.taxonomy.evaluation_cli } }
    "web-test" { Invoke-Step "web-test" { npm.cmd run web:test } }
    "web-build" { Invoke-Step "web-build" { npm.cmd run web:build } }
    "benchmark-analytics" {
        if (-not $env:BENCHMARK_DATABASE_URL) { throw "BENCHMARK_DATABASE_URL is required" }
        if (-not $env:CORPUS_SNAPSHOT_ID) { throw "CORPUS_SNAPSHOT_ID is required" }
        if (-not $env:ANALYTICS_RUN_ID) { throw "ANALYTICS_RUN_ID is required" }
        if (-not $env:EVIDENCE_SNAPSHOT_ID) { throw "EVIDENCE_SNAPSHOT_ID is required" }
        Invoke-Step "benchmark-analytics" { & $python benchmarks/run_analytics.py --database-url $env:BENCHMARK_DATABASE_URL --snapshot $env:CORPUS_SNAPSHOT_ID --run $env:ANALYTICS_RUN_ID --evidence $env:EVIDENCE_SNAPSHOT_ID --output data/benchmarks/analytics/query-report.json }
    }
    "migrate" {
        if (-not $env:DATABASE_URL) { throw "DATABASE_URL is required" }
        Invoke-Step "migrate" { & $python -m alembic upgrade head }
    }
    "build" {
        if (Test-Path -LiteralPath (Join-Path $PSScriptRoot "..\dist")) {
            Remove-Item -Recurse -Force -LiteralPath (Join-Path $PSScriptRoot "..\dist")
        }
        Invoke-Step "python build" { & $python -m pip wheel . --no-deps --wheel-dir dist }
        Invoke-Step "web build" { npm.cmd run web:build }
    }
    "ci" {
        Invoke-Step "format-check" { & $python -m ruff format --check . }
        Invoke-Step "python lint" { & $python -m ruff check . }
        Invoke-Step "python typecheck" { & $python -m mypy }
        Invoke-Step "python test-unit" { & $python -m pytest -m "not integration" }
        Invoke-Step "web lint" { npm.cmd run web:lint }
        Invoke-Step "web typecheck" { npm.cmd run web:typecheck }
        Invoke-Step "web test" { npm.cmd run web:test }
        if (Test-Path -LiteralPath (Join-Path $PSScriptRoot "..\dist")) {
            Remove-Item -Recurse -Force -LiteralPath (Join-Path $PSScriptRoot "..\dist")
        }
        Invoke-Step "python build" { & $python -m pip wheel . --no-deps --wheel-dir dist }
        Invoke-Step "web build" { npm.cmd run web:build }
    }
}
