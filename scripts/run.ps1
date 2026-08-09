# SecondMind launcher (PowerShell, Windows).
#
# Never assumes py, python, or python3 exist -- probes what's actually on
# PATH at runtime, in this order: py, python, python3 (matching run.bat's
# order; "py" is the officially recommended python.org launcher).
#
# Verified on windows-latest via .github/workflows/ci.yml -- not just
# claimed to work.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

$candidates = @("py", "python", "python3")
$chosen = $null
foreach ($c in $candidates) {
    if (Get-Command $c -ErrorAction SilentlyContinue) {
        $chosen = $c
        break
    }
}

if (-not $chosen) {
    Write-Error "secondmind: no Python 3 interpreter found on PATH (tried: py, python, python3). Install Python 3.9+ from https://www.python.org/downloads/ and try again."
    exit 127
}

if ($chosen -eq "py") {
    & py -3 -m secondmind @args
} else {
    & $chosen -m secondmind @args
}
exit $LASTEXITCODE
