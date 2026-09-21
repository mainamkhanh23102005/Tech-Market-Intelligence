param(
    [Parameter(Position = 0)]
    [ValidateSet("format", "format-check", "lint", "typecheck", "test", "test-unit", "test-integration", "build", "migrate", "ci")]
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
    "lint" { Invoke-Step "lint" { & $python -m ruff check . } }
    "typecheck" { Invoke-Step "typecheck" { & $python -m mypy } }
    "test" { Invoke-Step "test" { & $python -m pytest -m "not integration" } }
    "test-unit" { Invoke-Step "test-unit" { & $python -m pytest -m "not integration" } }
    "test-integration" { Invoke-Step "test-integration" { & $python -m pytest -m integration } }
    "migrate" {
        if (-not $env:DATABASE_URL) { throw "DATABASE_URL is required" }
        Invoke-Step "migrate" { & $python -m alembic upgrade head }
    }
    "build" {
        if (Test-Path -LiteralPath (Join-Path $PSScriptRoot "..\dist")) {
            Remove-Item -Recurse -Force -LiteralPath (Join-Path $PSScriptRoot "..\dist")
        }
        Invoke-Step "build" { & $python -m pip wheel . --no-deps --wheel-dir dist }
    }
    "ci" {
        Invoke-Step "format-check" { & $python -m ruff format --check . }
        Invoke-Step "lint" { & $python -m ruff check . }
        Invoke-Step "typecheck" { & $python -m mypy }
        Invoke-Step "test-unit" { & $python -m pytest -m "not integration" }
        if (Test-Path -LiteralPath (Join-Path $PSScriptRoot "..\dist")) {
            Remove-Item -Recurse -Force -LiteralPath (Join-Path $PSScriptRoot "..\dist")
        }
        Invoke-Step "build" { & $python -m pip wheel . --no-deps --wheel-dir dist }
    }
}
