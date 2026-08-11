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

rem REPO_ROOT comes from SECONDMIND_REPO_DIR (the manifest's repo_dir
rem user_config field), never from this script's own location -- Claude
rem Desktop copies the whole claude-desktop-extension\ folder into its own
rem private storage on install, so "the directory above this script" is
rem Claude Desktop's extension cache, not the actual cloned repo. Confirmed
rem by reproducing this exact failure on a real machine: it produced
rem "ModuleNotFoundError: No module named 'secondmind_mcp'" because
rem --directory pointed at the wrong place.
set REPO_ROOT=%SECONDMIND_REPO_DIR%
if "%REPO_ROOT%"=="" (
    echo secondmind: SECONDMIND_REPO_DIR is not set. 1>&2
    echo Open Claude Desktop -^> Settings -^> Extensions -^> secondmind -^> Configure, 1>&2
    echo and set 'SecondMind repo location' to the folder where you cloned 1>&2
    echo https://github.com/al-amin/SecondMind ^(the folder containing pyproject.toml^). 1>&2
    exit /b 1
)
if not exist "%REPO_ROOT%\pyproject.toml" (
    echo secondmind: "%REPO_ROOT%" does not look like a SecondMind clone ^(no pyproject.toml^). 1>&2
    echo Check the 'SecondMind repo location' value in Claude Desktop's Configure dialog. 1>&2
    exit /b 1
)

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
