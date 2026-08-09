@echo off
rem SecondMind launcher (native Windows cmd.exe).
rem
rem Never assumes py, python, or python3 exist -- probes what's actually on
rem PATH at runtime, in this order: py -3, python, python3. Real Windows
rem installs from python.org register the "py" launcher, the officially
rem recommended entry point and the most reliable of the three; "python"/
rem "python3" are checked as fallbacks for other install methods (Microsoft
rem Store, manual PATH setup, etc).
rem
rem Verified on windows-latest via .github/workflows/ci.yml — not just
rem claimed to work.

setlocal
set REPO_ROOT=%~dp0..
cd /d "%REPO_ROOT%"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 -m secondmind %*
    exit /b %ERRORLEVEL%
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python -m secondmind %*
    exit /b %ERRORLEVEL%
)

where python3 >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    python3 -m secondmind %*
    exit /b %ERRORLEVEL%
)

echo secondmind: no Python 3 interpreter found on PATH (tried: py, python, python3). 1>&2
echo Install Python 3.9+ from https://www.python.org/downloads/ and try again. 1>&2
exit /b 127
