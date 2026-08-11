"""SecondMind self-diagnosis — one command, no help needed from anyone.

Checks everything that can make SecondMind fail to start, in the order a
human would debug it: Python, uv, the venv, the vault, and both client
registrations (Claude Desktop's config file, Claude Code's ``claude mcp
list``). Every check prints PASS/FAIL/WARN plus the exact next command to
run — never just "it's broken."

Zero dependencies beyond the stdlib, runs with a bare ``python3`` on any
platform (Windows/macOS/Linux) — this has to work even when everything
else SecondMind needs is still missing, so it cannot import ``secondmind``
or anything that could itself be the reason it fails to run. Path
resolution logic below is intentionally re-implemented rather than
imported from :mod:`secondmind.paths`, for that same reason.

Run with:

    python3 scripts/diagnose.py
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

_RESULTS: list[tuple[str, str, str]] = []  # (status, check, detail)


def _record(status: str, check: str, detail: str) -> None:
    _RESULTS.append((status, check, detail))
    marker = {"PASS": "[ OK ]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[status]
    print(f"{marker} {check}")
    if detail:
        for line in detail.splitlines():
            print(f"       {line}")


def _run(args: list[str], timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, check=False
    )


def check_platform() -> None:
    print("\n== Platform ==")
    _record(
        "PASS",
        "Operating system",
        f"{platform.system()} {platform.release()} ({platform.machine()})",
    )


def check_python() -> None:
    print("\n== Python ==")
    version = sys.version_info
    detail = f"{sys.executable} — Python {platform.python_version()}"
    if version >= (3, 10):
        _record("PASS", "Python interpreter", detail)
    else:
        _record(
            "FAIL",
            "Python interpreter",
            f"{detail}\nsecondmind_mcp requires Python >= 3.10 (mcp>=2.0's own requirement).\n"
            "Install a newer Python from https://www.python.org/downloads/ or via uv "
            "(uv automatically manages its own Python versions, so this may not block you).",
        )

    # On Windows, uv's venvs only ever produce python.exe — python3.exe is
    # a macOS/Linux-only alias. A bare "python3" on PATH here is not
    # required for SecondMind itself (uv resolves its own interpreter),
    # but its ABSENCE is exactly what caused a real bug this diagnostic
    # exists to catch early: any script that still hardcodes "python3"
    # after "uv run" would silently fail on this machine.
    if platform.system() == "Windows":
        python3_path = shutil.which("python3")
        if python3_path:
            _record("PASS", "python3 on PATH (Windows)", python3_path)
        else:
            _record(
                "WARN",
                "python3 on PATH (Windows)",
                "No 'python3' command found — normal on Windows (uv/venvs only create "
                "python.exe here). Only matters if some other tool assumes 'python3' "
                "specifically; SecondMind's own launchers no longer do.",
            )


def check_uv() -> str | None:
    print("\n== uv ==")
    uv_path = shutil.which("uv")
    candidates = [
        uv_path,
        str(Path.home() / ".local" / "bin" / ("uv.exe" if platform.system() == "Windows" else "uv")),
        str(Path.home() / ".cargo" / "bin" / ("uv.exe" if platform.system() == "Windows" else "uv")),
        "/opt/homebrew/bin/uv",
        "/usr/local/bin/uv",
    ]
    resolved = next((c for c in candidates if c and Path(c).exists()), None)

    if resolved is None:
        _record(
            "FAIL",
            "uv installed",
            "No 'uv' executable found on PATH or in common install locations "
            f"({', '.join(c for c in candidates[1:] if c)}).\n"
            "Install it: https://docs.astral.sh/uv/getting-started/installation/",
        )
        return None

    try:
        result = _run([resolved, "--version"])
        version = result.stdout.strip() or result.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        _record("FAIL", "uv installed", f"Found at {resolved} but failed to run: {exc}")
        return None

    on_path = " (on PATH)" if resolved == uv_path else " (NOT on PATH — found via fallback probing)"
    _record("PASS", "uv installed", f"{resolved}{on_path}\n{version}")
    return resolved


def check_venv(uv_path: str | None, repo_root: Path) -> None:
    print("\n== SecondMind venv ==")
    if uv_path is None:
        _record("FAIL", "uv run --extra mcp resolves", "Skipped — uv not found above.")
        return

    try:
        result = _run(
            [uv_path, "run", "--directory", str(repo_root), "--extra", "mcp", "-m", "secondmind", "--help"],
            timeout=120.0,
        )
    except subprocess.TimeoutExpired:
        _record(
            "FAIL",
            "uv run --extra mcp resolves",
            "Timed out after 120s — first run downloads/builds the venv; a slow or "
            "offline network connection can cause this. Try running the command below "
            "by hand and watch for the actual error:\n"
            f"  uv run --directory \"{repo_root}\" --extra mcp -m secondmind --help",
        )
        return

    if result.returncode == 0:
        _record("PASS", "uv run --extra mcp resolves", "venv builds and secondmind CLI runs.")
    else:
        _record(
            "FAIL",
            "uv run --extra mcp resolves",
            f"Exit code {result.returncode}.\n"
            f"stdout: {result.stdout.strip()[-500:]}\n"
            f"stderr: {result.stderr.strip()[-500:]}",
        )


def _default_vault_root() -> Path:
    override = os.environ.get("SECONDMIND_VAULT")
    return Path(override) if override else Path.home() / ".secondmind" / "vault"


def _default_index_db() -> Path:
    override = os.environ.get("SECONDMIND_INDEX_DB")
    return Path(override) if override else Path.home() / ".secondmind" / "index.db"


def check_vault() -> None:
    print("\n== Vault ==")
    vault_root = _default_vault_root()
    index_db = _default_index_db()

    source = "SECONDMIND_VAULT env var" if os.environ.get("SECONDMIND_VAULT") else "default (~/.secondmind/vault)"
    _record("PASS", "Vault path resolved", f"{vault_root}  [{source}]")

    if not vault_root.exists():
        _record(
            "WARN",
            "Vault directory exists",
            f"{vault_root} does not exist yet — normal for a brand-new install. "
            "It is created automatically on the first note you save; not an error.",
        )
    else:
        try:
            notes = list(vault_root.glob("*.md"))
        except OSError as exc:
            _record("FAIL", "Vault directory readable", f"{vault_root}: {exc}")
        else:
            _record("PASS", "Vault directory readable", f"{len(notes)} note(s) found.")
            test_file = vault_root / f".secondmind-diagnose-write-test-{os.getpid()}"
            try:
                test_file.write_text("x", encoding="utf-8")
                test_file.unlink()
                _record("PASS", "Vault directory writable", str(vault_root))
            except OSError as exc:
                _record(
                    "FAIL",
                    "Vault directory writable",
                    f"{vault_root}: {exc}\nCheck folder permissions, or that no other "
                    "process (antivirus, sync client) has it locked.",
                )

    if index_db.exists():
        _record("PASS", "Search index present", f"{index_db} ({index_db.stat().st_size} bytes)")
    else:
        _record(
            "WARN",
            "Search index present",
            f"{index_db} does not exist yet — created on first put/rebuild, "
            "or after a fresh install. Not an error.",
        )


def _claude_desktop_config_path() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def _claude_desktop_log_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Logs" / "Claude"
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "Claude" / "logs"
    return Path.home() / ".config" / "Claude" / "logs"


def check_claude_desktop() -> None:
    print("\n== Claude Desktop ==")
    config_path = _claude_desktop_config_path()

    if not config_path.exists():
        _record(
            "WARN",
            "Claude Desktop config found",
            f"{config_path} does not exist — Claude Desktop may not be installed, or "
            "SecondMind hasn't been registered via a manual config edit (installing the "
            "unpacked extension does not need this file).",
        )
    else:
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _record(
                "FAIL",
                "Claude Desktop config valid",
                f"{config_path} exists but failed to parse: {exc}\n"
                "A malformed config can silently prevent ALL MCP servers from loading, "
                "not just SecondMind. Fix the JSON syntax, then fully restart Claude Desktop.",
            )
        else:
            servers = config.get("mcpServers", {})
            if "secondmind" in servers:
                _record("PASS", "Claude Desktop config valid", f"{config_path}\nsecondmind entry found.")
            else:
                _record(
                    "WARN",
                    "secondmind registered in Claude Desktop config",
                    f"{config_path} is valid JSON but has no 'secondmind' entry under "
                    "mcpServers. If you installed the unpacked extension instead, this is "
                    "expected — the extension does not use this file.",
                )

    extensions_dir = None
    if platform.system() == "Darwin":
        extensions_dir = Path.home() / "Library" / "Application Support" / "Claude" / "Claude Extensions"
    elif platform.system() == "Windows":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        extensions_dir = base / "Claude" / "Claude Extensions"

    if extensions_dir is not None and extensions_dir.exists():
        matches = [p for p in extensions_dir.iterdir() if "secondmind" in p.name.lower()]
        if matches:
            _record("PASS", "SecondMind extension installed", f"{matches[0]}")
        else:
            _record(
                "WARN",
                "SecondMind extension installed",
                f"No secondmind-named folder under {extensions_dir}. Not installed as an "
                "unpacked extension — expected if you registered it manually instead.",
            )

    log_dir = _claude_desktop_log_dir()
    log_path = log_dir / "mcp-server-SecondMind.log"
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        # Only ever report line-level signals, never full log content —
        # a "Message from client/server" line can contain a note's real
        # title/body verbatim (confirmed on this machine's own log), and
        # this is a local-first, no-PII-off-box tool by design (SPEC.md
        # §11) — a diagnostic script is exactly the kind of place that
        # promise must hold too, since its output is the thing most
        # likely to get pasted into a support channel.
        error_signals = [
            "Traceback",
            "not recognized as an internal or external command",
            "ModuleNotFoundError",
            "[error]",
        ]
        matches = [line for line in lines[-200:] if any(sig in line for sig in error_signals)]
        if matches:
            _record(
                "FAIL",
                "SecondMind MCP server log — recent errors found",
                "\n".join(m.split("{ metadata:")[0].strip() for m in matches[-5:]),
            )
        else:
            _record(
                "PASS",
                "SecondMind MCP server log — no recent errors",
                f"{log_path} ({len(lines)} lines total, checked last 200).",
            )
    else:
        _record(
            "WARN",
            "SecondMind MCP server log found",
            f"{log_path} does not exist — SecondMind has never been launched by "
            "Claude Desktop yet, or logs live elsewhere on this install.",
        )


def check_claude_code() -> None:
    print("\n== Claude Code ==")
    claude_path = shutil.which("claude")
    if claude_path is None:
        _record(
            "WARN",
            "claude CLI found",
            "'claude' not found on PATH — Claude Code may not be installed, or not on PATH.",
        )
        return

    try:
        result = _run([claude_path, "mcp", "list"], timeout=30.0)
    except subprocess.TimeoutExpired:
        _record("FAIL", "claude mcp list", "Timed out after 30s.")
        return
    except OSError as exc:
        _record("FAIL", "claude mcp list", f"Failed to run: {exc}")
        return

    output = result.stdout + result.stderr
    if "secondmind" not in output.lower():
        _record(
            "WARN",
            "secondmind registered in Claude Code",
            "No 'secondmind' entry in `claude mcp list`. Register it with:\n"
            '  claude mcp add secondmind -- uv run --directory "$(pwd)" --extra mcp '
            "-m secondmind_mcp.server",
        )
        return

    secondmind_line = next((line for line in output.splitlines() if "secondmind" in line.lower()), "")
    if "✔" in secondmind_line or "connected" in secondmind_line.lower():
        _record("PASS", "secondmind registered in Claude Code", secondmind_line.strip())
    else:
        _record(
            "FAIL",
            "secondmind connected in Claude Code",
            f"{secondmind_line.strip()}\nRun the command by hand to see the real error:\n"
            "  claude mcp list",
        )


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    print("SecondMind diagnostics")
    print(f"Repo root: {repo_root}")

    check_platform()
    check_python()
    uv_path = check_uv()
    check_venv(uv_path, repo_root)
    check_vault()
    check_claude_desktop()
    check_claude_code()

    failed = [r for r in _RESULTS if r[0] == "FAIL"]
    warned = [r for r in _RESULTS if r[0] == "WARN"]

    print(f"\n{'=' * 60}")
    print(f"Summary: {len(_RESULTS) - len(failed) - len(warned)} passed, "
          f"{len(warned)} warnings, {len(failed)} failed.")

    if failed:
        print("\nFix these first, in order — each blocks the ones after it:")
        for status, check, _ in failed:
            print(f"  - {check}")
        return 1

    if warned:
        print("\nEverything required passed. Warnings above are informational, "
              "not blockers, for a fresh install.")
    else:
        print("\nAll checks passed — SecondMind should be working end to end.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
