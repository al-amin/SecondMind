@echo off
rem SecondMind diagnostics entry point (native Windows cmd.exe).
rem
rem diagnose.py itself needs Python to already exist to run at all, so it
rem can never diagnose "Python is completely missing" from inside itself.
rem This wrapper is plain batch -- no Python required -- and its only job
rem is to answer that one question first: does ANY Python interpreter
rem exist on PATH? If not, stop here with a clear install link instead of
rem a cryptic "'python' is not recognized" error. Only once that's
rem confirmed does it hand off to diagnose.py for everything else.
rem
rem Probes py -3, then python, then python3 -- same order and same
rem reasoning as scripts/run.bat: real Windows installs from python.org
rem register the "py" launcher as the officially recommended entry point;
rem "python"/"python3" are checked as fallbacks for other install methods.

setlocal enabledelayedexpansion
set SCRIPT_DIR=%~dp0

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 "%SCRIPT_DIR%diagnose.py"
    exit /b !ERRORLEVEL!
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python "%SCRIPT_DIR%diagnose.py"
    exit /b !ERRORLEVEL!
)

where python3 >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python3 "%SCRIPT_DIR%diagnose.py"
    exit /b !ERRORLEVEL!
)

echo secondmind: no Python interpreter found on PATH at all (tried: py, python, python3). 1>&2
echo This means SecondMind cannot run yet -- nothing to diagnose beyond this. 1>&2
echo Install Python from https://www.python.org/downloads/ (check "Add python.exe to PATH" 1>&2
echo during setup), then run this script again. 1>&2
exit /b 127
