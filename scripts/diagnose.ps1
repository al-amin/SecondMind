# SecondMind diagnostics entry point (PowerShell, Windows).
#
# diagnose.py itself needs Python to already exist to run at all, so it
# can never diagnose "Python is completely missing" from inside itself.
# This wrapper is plain PowerShell -- no Python required -- and its only
# job is to answer that one question first: does ANY Python interpreter
# exist on PATH? If not, stop here with a clear install link instead of a
# cryptic "term not recognized" error. Only once that's confirmed does it
# hand off to diagnose.py for everything else.
#
# Probes py, then python, then python3 -- same order and same reasoning
# as scripts/run.ps1: real Windows installs from python.org register the
# "py" launcher as the officially recommended entry point.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DiagnosePy = Join-Path $ScriptDir "diagnose.py"

$candidates = @("py", "python", "python3")
$chosen = $null
foreach ($c in $candidates) {
    if (Get-Command $c -ErrorAction SilentlyContinue) {
        $chosen = $c
        break
    }
}

if (-not $chosen) {
    Write-Error "secondmind: no Python interpreter found on PATH at all (tried: py, python, python3). This means SecondMind cannot run yet -- nothing to diagnose beyond this. Install Python from https://www.python.org/downloads/ (check `"Add python.exe to PATH`" during setup), then run this script again."
    exit 127
}

if ($chosen -eq "py") {
    & py -3 $DiagnosePy
} else {
    & $chosen $DiagnosePy
}
exit $LASTEXITCODE
