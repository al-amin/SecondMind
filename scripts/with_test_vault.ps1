# Run a SecondMind command against a named disposable test vault.
#
# Collapses the repeated
#   $env:SECONDMIND_VAULT = ...\.secondmind-<profile>\vault
#   $env:SECONDMIND_INDEX_DB = ...\.secondmind-<profile>\index.db
#   uv run --extra mcp python3 ...
# pattern from TESTING_WITH_CLAUDE.md into one line per command.
#
# Usage:
#   scripts/with_test_vault.ps1 <profile> <command> [args...]
#
# Example:
#   scripts/with_test_vault.ps1 test -m secondmind search "orange sunset"

$ErrorActionPreference = "Stop"

if ($args.Count -lt 2) {
    Write-Error "usage: with_test_vault.ps1 <profile> <command> [args...]`n  e.g.: with_test_vault.ps1 test -m secondmind search `"orange sunset`""
    exit 64
}

$Profile_ = $args[0]
$Rest = $args[1..($args.Count - 1)]

if ($Profile_ -match '[\\/]' -or $Profile_ -eq '..' -or $Profile_ -eq '') {
    Write-Error "secondmind: invalid profile name '$Profile_' -- use a plain name like 'test', not a path"
    exit 64
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "secondmind: 'uv' not found on PATH -- install it from https://docs.astral.sh/uv/ first."
    exit 127
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$Base = Join-Path $HOME ".secondmind-$Profile_"
$env:SECONDMIND_VAULT = Join-Path $Base "vault"
$env:SECONDMIND_INDEX_DB = Join-Path $Base "index.db"

Write-Host "secondmind: profile '$Profile_' -> vault=$($env:SECONDMIND_VAULT)"

& uv run --directory $RepoRoot --extra mcp @Rest
exit $LASTEXITCODE
