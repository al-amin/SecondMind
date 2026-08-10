# Testing SecondMind with Claude Desktop and Claude Code

This is the real, end-to-end verification the automated tests can't do: register SecondMind as
an actual MCP server with real Claude clients, then run the exact flow — save via one client,
retrieve from another, export the vault, import it into a fresh location, verify it's still
there.

Everything below was verified against this exact machine and the `v2` branch before being
written down — no guessed paths, no assumed config formats.

## Prerequisites

```bash
cd /Users/al.amin1/dev/personal/gitHub_personal/SecondMind
git checkout v2   # or main, once v2 is merged
uv run --extra mcp python3 scripts/live_probe.py
```

If that prints `Live probe PASSED — all 8 tools verified over a real stdio subprocess.`, the
server itself works. Everything past this point is testing the *client* side — Claude Desktop
and Claude Code actually spawning and talking to it.

**Why `uv run --extra mcp` and not plain `python3 -m secondmind_mcp.server`:** this machine's
default `python3` resolves to an unrelated project's venv pinned at `mcp==1.27.1` — SecondMind's
v2 code needs `mcp>=2.0`. `uv run` creates and uses SecondMind's own isolated environment every
time, so this exact command is what should go in both clients' configs — never a bare `python3`
that depends on whatever happens to be on `PATH`.

You may see `warning: VIRTUAL_ENV=... does not match the project environment path` in the
output whenever a different project's venv is active in your shell — this is harmless, `uv run`
still uses SecondMind's own `.venv` regardless. Every command below was actually run once to
confirm this.

---

## Part 1 — Register with Claude Desktop

### Option A — Install as an unpacked extension (recommended, no config editing)

A ready-made extension package lives at `claude-desktop-extension/` in this repo, following
the exact `manifest_version 0.3` schema already proven working on this machine (the existing
`al-amin-mcp`/AUPS extension uses the same shape — `manifest.json` + `run.sh` + `icon.png`).

1. Claude Desktop → **Settings → Extensions → Install Unpacked Extension**
2. Select the folder:
   `/Users/al.amin1/dev/personal/gitHub_personal/SecondMind/claude-desktop-extension`
3. It appears under "Installed on your computer" next to AUPS, with a **Configure** button.
4. Fully quit and reopen Claude Desktop (see restart instructions below — closing the window
   is not enough).

This is the easier path — skip straight to "Verify it connected" below. Use Option B only if
you want to hand-edit the config directly, or the extension install fails for some reason.

**Vault location:** the packaged extension's `manifest.json` already sets
`SECONDMIND_VAULT`/`SECONDMIND_INDEX_DB` to the same `-test` path Part 2's Claude Code command
below uses — so Option A and Part 2 point at the same vault out of the box, which is what
makes Part 3's cross-client test actually work without any manual edit. (Earlier drafts of
this extension left `env` empty, defaulting to the real `~/.secondmind/vault` — verified this
was a real inconsistency, not just a theoretical one: manual testing had already put a note in
the real default vault before this fix, which would have silently mixed real and test data if
left as-is.) Once you're done testing and want SecondMind for real everyday use, remove the
`env` overrides from `claude-desktop-extension/manifest.json` (or just don't install this
extension at all — point a fresh install at the real default instead).

### Option B — Manual `claude_desktop_config.json` edit

**Config file** (confirmed on this machine):
`~/Library/Application Support/Claude/claude_desktop_config.json`

Open it and add a `secondmind` entry under the existing `mcpServers` key (your `al-amin-mcp`
router entry will already be there — leave it, just add `secondmind` alongside it):

```json
{
  "mcpServers": {
    "al-amin-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "...", "mcp-allianz-router", "..."]
    },
    "secondmind": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/Users/al.amin1/dev/personal/gitHub_personal/SecondMind",
        "--extra", "mcp",
        "python3", "-m", "secondmind_mcp.server"
      ],
      "env": {
        "SECONDMIND_VAULT": "/Users/al.amin1/.secondmind-test/vault",
        "SECONDMIND_INDEX_DB": "/Users/al.amin1/.secondmind-test/index.db"
      }
    }
  }
}
```

`SECONDMIND_VAULT`/`SECONDMIND_INDEX_DB` are optional — omit them and it defaults to
`~/.secondmind/vault` and `~/.secondmind/index.db`. Setting them explicitly to a `-test`
location for this first run means you can delete that folder afterward without touching
anything real.

**Validate the JSON, then restart Claude Desktop fully — closing the window is not enough:**

```bash
jq empty ~/Library/Application\ Support/Claude/claude_desktop_config.json && echo "valid JSON"
killall Claude
sleep 2
open -a Claude
```

**Verify it connected:** in a new chat, click the tools icon (bottom of the message box) —
`secondmind` should be listed. If it's missing, check the logs before anything else:

```bash
tail -50 ~/Library/Logs/Claude/mcp-server-secondmind.log
tail -50 ~/Library/Logs/Claude/mcp.log
```

A working startup looks like a clean `initialize` handshake with no Python traceback in the
server-specific log. A `ModuleNotFoundError` there means the `uv run --directory ... --extra
mcp` arguments weren't copied exactly — that's almost always the cause.

---

## Part 2 — Register with Claude Code

Claude Code has its own registration command — don't hand-edit a JSON file for this one:

```bash
claude mcp add secondmind \
  -e SECONDMIND_VAULT=/Users/al.amin1/.secondmind-test/vault \
  -e SECONDMIND_INDEX_DB=/Users/al.amin1/.secondmind-test/index.db \
  -- uv run --directory /Users/al.amin1/dev/personal/gitHub_personal/SecondMind --extra mcp python3 -m secondmind_mcp.server
```

Confirm it registered and is healthy:

```bash
claude mcp list
```

You should see `secondmind: ... - ✔ Connected` in the output (matching the format of your
existing `lean-ctx`/`context-mode` entries).

**Note:** if you used the *same* `SECONDMIND_VAULT` path in both Part 1 and Part 2, both clients
now point at the same vault — that's what makes the cross-client flow below actually meaningful.
If you used different paths, skip to Part 4 (export/import) instead of Part 3.

---

## Part 3 — The real cross-client flow (same vault)

This is the test that actually proves the promise: *save in one client, recall in another.*

1. **In Claude Desktop**, start a new chat and say:
   > Remember that my SecondMind test note says "the sky was orange at sunset on August 10th."

   Claude should call `secondmind_put` (you'll see a tool-use indicator). If it doesn't
   spontaneously use the tool, be explicit: "Use the secondmind tool to save this."

2. **In Claude Code**, in a fresh session (new terminal, new `claude` invocation — not a
   continuation of anything), ask:
   > What does my SecondMind note say about the sky?

   Claude Code should call `secondmind_search` or `secondmind_get_recent` and surface the exact
   note you saved from Desktop. This is the actual "any session, any client" claim — verified,
   not assumed.

---

## Part 4 — Export from one, import into the other

This is worth testing even if Part 3 already worked, because it's the *documented* portability
path (SPEC.md §7) rather than relying on both clients happening to share a vault path.

The CLI takes the vault/index location from `SECONDMIND_VAULT`/`SECONDMIND_INDEX_DB` env vars
only — there is no `--vault` flag (confirmed by reading `secondmind/cli.py` directly, not
assumed).

1. **Export** (from either client, or the CLI directly):
   ```bash
   SECONDMIND_VAULT=/Users/al.amin1/.secondmind-test/vault \
   uv run --extra mcp python3 -m secondmind export --output /tmp/secondmind-export.json
   cat /tmp/secondmind-export.json
   ```
   Or ask either Claude client: "Export my SecondMind vault to /tmp/secondmind-export.json."

2. **Import into a fresh, separate vault** (proving it's not the same files):
   ```bash
   SECONDMIND_VAULT=/Users/al.amin1/.secondmind-import-test/vault \
   SECONDMIND_INDEX_DB=/Users/al.amin1/.secondmind-import-test/index.db \
   uv run --extra mcp python3 -m secondmind import /tmp/secondmind-export.json

   SECONDMIND_VAULT=/Users/al.amin1/.secondmind-import-test/vault \
   SECONDMIND_INDEX_DB=/Users/al.amin1/.secondmind-import-test/index.db \
   uv run --extra mcp python3 -m secondmind rebuild

   SECONDMIND_VAULT=/Users/al.amin1/.secondmind-import-test/vault \
   SECONDMIND_INDEX_DB=/Users/al.amin1/.secondmind-import-test/index.db \
   uv run --extra mcp python3 -m secondmind search "orange sunset"
   ```
   The search result should show your note, now living in a completely separate vault
   directory that never existed before this command.

---

## Cleanup

Once you're satisfied it works, remove the test vaults (never the real ones, if you've since
started using SecondMind for real):

```bash
rm -rf /Users/al.amin1/.secondmind-test /Users/al.amin1/.secondmind-import-test /tmp/secondmind-export.json
```

To remove the MCP registrations:

```bash
claude mcp remove secondmind
# and manually delete the "secondmind" entry from
# ~/Library/Application Support/Claude/claude_desktop_config.json, then restart Claude Desktop
```

---

## If something doesn't work

| Symptom | Likely cause | Check |
|---|---|---|
| Tools icon missing in Desktop | Config JSON malformed, or server crashed on startup | `jq empty` the config; `tail ~/Library/Logs/Claude/mcp-server-secondmind.log` |
| `claude mcp list` shows `✘ Failed to connect` | Wrong `--directory` path, or `uv`/`--extra mcp` args copied incorrectly | Run the exact same command by hand in a terminal — the real error will print directly |
| Desktop connects but tool calls fail | Server started but crashed on a specific call | `tail -f ~/Library/Logs/Claude/mcp-server-secondmind.log` while retrying the tool call in Claude |
| `ModuleNotFoundError: No module named 'mcp'` | A client bypassed `uv run` and used a bare `python3` that doesn't have `mcp` installed | Re-check the config uses `uv run --directory ... --extra mcp python3 ...`, not a bare interpreter path |
| Search finds nothing after `put` worked | Normal for `import`/`migrate` (they don't auto-index) — not for `put` (which does) | Run `secondmind rebuild` (via CLI or ask Claude to call the rebuild path) |
