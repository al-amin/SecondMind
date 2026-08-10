@echo off
rem Run a SecondMind command against a named disposable test vault.
rem
rem Collapses the repeated
rem   set SECONDMIND_VAULT=%%USERPROFILE%%\.secondmind-<profile>\vault
rem   set SECONDMIND_INDEX_DB=%%USERPROFILE%%\.secondmind-<profile>\index.db
rem   uv run --extra mcp python3 ...
rem pattern from TESTING_WITH_CLAUDE.md into one line per command.
rem
rem Usage:
rem   scripts\with_test_vault.bat <profile> <command> [args...]
rem
rem Example:
rem   scripts\with_test_vault.bat test -m secondmind search "orange sunset"

setlocal enabledelayedexpansion

if "%~1"=="" goto usage
if "%~2"=="" goto usage

set PROFILE=%~1
shift

echo %PROFILE% | findstr /r /c:"[\\/]" >nul
if %ERRORLEVEL% EQU 0 (
    echo secondmind: invalid profile name '%PROFILE%' -- use a plain name like 'test', not a path 1>&2
    exit /b 64
)

where uv >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo secondmind: 'uv' not found on PATH -- install it from https://docs.astral.sh/uv/ first. 1>&2
    exit /b 127
)

set SCRIPT_DIR=%~dp0
set REPO_ROOT=%SCRIPT_DIR%..
set SECONDMIND_VAULT=%USERPROFILE%\.secondmind-%PROFILE%\vault
set SECONDMIND_INDEX_DB=%USERPROFILE%\.secondmind-%PROFILE%\index.db

echo secondmind: profile '%PROFILE%' -^> vault=%SECONDMIND_VAULT% 1>&2

rem %* still includes the consumed %1 (profile) — shift does not remove it
rem from %*  in cmd.exe, so rebuild the remaining args explicitly instead.
set REST=
:collect
if "%~1"=="" goto run
set REST=!REST! %1
shift
goto collect

:run
uv run --directory "%REPO_ROOT%" --extra mcp !REST!
exit /b %ERRORLEVEL%

:usage
echo usage: %~nx0 ^<profile^> ^<command^> [args...] 1>&2
echo   e.g.: %~nx0 test -m secondmind search "orange sunset" 1>&2
exit /b 64
