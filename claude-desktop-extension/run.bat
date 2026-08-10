@echo off
rem SecondMind MCP server launcher for the Claude Desktop extension (Windows).
rem
rem manifest.json's platform_overrides.win32 points here instead of run.sh --
rem cmd.exe has no shebang interpreter, so it cannot execute a .sh file
rem directly (confirmed on a real Windows install: "'sh' is not recognized
rem as an internal or external command"). Probes common uv install
rem locations, mirroring scripts/run.bat's proven pattern, since extension
rem processes can launch with a PATH that doesn't include wherever uv was
rem installed.

setlocal enabledelayedexpansion
set REPO_ROOT=%~dp0..

rem !ERRORLEVEL! (delayed expansion), not %ERRORLEVEL% -- inside a
rem parenthesized if-block, %VAR% is substituted once at parse time
rem (before uv run even executes), so exit /b %ERRORLEVEL% would always
rem report the preceding "where"/"exist" check's result, never uv's real
rem exit code.

where uv >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    uv run --directory "%REPO_ROOT%" --extra mcp -m secondmind_mcp.server
    exit /b !ERRORLEVEL!
)

if exist "%USERPROFILE%\.local\bin\uv.exe" (
    "%USERPROFILE%\.local\bin\uv.exe" run --directory "%REPO_ROOT%" --extra mcp -m secondmind_mcp.server
    exit /b !ERRORLEVEL!
)

if exist "%USERPROFILE%\.cargo\bin\uv.exe" (
    "%USERPROFILE%\.cargo\bin\uv.exe" run --directory "%REPO_ROOT%" --extra mcp -m secondmind_mcp.server
    exit /b !ERRORLEVEL!
)

echo secondmind: no 'uv' executable found (checked PATH, %%USERPROFILE%%\.local\bin, %%USERPROFILE%%\.cargo\bin). 1>&2
echo Install uv from https://docs.astral.sh/uv/getting-started/installation/ and try again. 1>&2
exit /b 127
