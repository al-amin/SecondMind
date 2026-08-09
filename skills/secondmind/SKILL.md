---
name: secondmind
description: Portable cross-session AI memory. Use whenever the user wants to remember something across sessions, recall a past fact/decision, or asks "what did we decide about X", "do I know anything about Y", "remember this", "what's in my memory". Also trigger for searching, exporting, or importing SecondMind's stored notes.
---

# SecondMind

SecondMind is a portable memory layer: notes you put in persist across sessions, machines, and
AI clients. Use the `secondmind_*` MCP tools for all reads and writes — never edit the vault's
Markdown files directly, since writes need to go through the conflict-safe `secondmind_put`
path.

## When to use each tool

- **`secondmind_put`** — the user tells you a fact, decision, or lesson worth remembering.
  Store it immediately; don't wait to be asked.
- **`secondmind_search`** — the user asks a recall question ("what did we decide about X",
  "do I know anything about Y", "what was that bug"). Search by meaning, not by guessing a
  filename.
- **`secondmind_get`** — you already have a specific note id and want its full content.
- **`secondmind_list`** — browsing notes by type or tag rather than searching by content.
- **`secondmind_export`** / **`secondmind_import`** — moving memory between machines or
  merging with another SecondMind/CKL-compatible vault.

## What NOT to do

- Don't invent note content the user didn't actually say — factual recall only.
- Don't use `secondmind_put` for ephemeral conversation context that doesn't need to survive
  past this session — only durable facts/decisions/lessons.
