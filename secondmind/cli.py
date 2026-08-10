"""python3 -m secondmind — the zero-install command-line interface.

Bounded-context responsibility: translate command-line arguments into
calls against :class:`secondmind.store.VaultStore` and
:class:`secondmind.sqlite_index.SqliteIndex`, and render results as JSON on
stdout. Every expected error condition (missing note, bad type, invalid
id) prints one line to stderr and returns a non-zero exit code — never a
raw traceback (SPEC.md §4).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from secondmind.models import KnowledgeType
from secondmind.paths import InvalidNoteIdError, default_index_db, default_vault_root
from secondmind.portability import export_bundle, import_bundle
from secondmind.semantic_embedder import load_embedder_from_env
from secondmind.sqlite_index import SqliteIndex
from secondmind.store import NoteNotFoundError, VaultStore


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="secondmind")
    subparsers = parser.add_subparsers(dest="command", required=True)

    put = subparsers.add_parser("put")
    put.add_argument("--id")
    put.add_argument("--type", required=True)
    put.add_argument("--title", required=True)
    put.add_argument("--body", required=True)
    put.add_argument("--tags", default="")
    put.add_argument("--scope", default="")
    put.add_argument("--ttl-days", type=int, default=None)

    get = subparsers.add_parser("get")
    get.add_argument("id")

    list_cmd = subparsers.add_parser("list")
    list_cmd.add_argument("--type")
    list_cmd.add_argument("--tag")

    search = subparsers.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--cursor", default=None)

    export = subparsers.add_parser("export")
    export.add_argument("--output", required=True)

    import_cmd = subparsers.add_parser("import")
    import_cmd.add_argument("path")
    import_cmd.add_argument("--dry-run", action="store_true")

    subparsers.add_parser("rebuild")

    return parser


def _item_to_dict(item: object) -> dict[str, object]:
    frontmatter, body = item.to_frontmatter()  # type: ignore[attr-defined]
    result = dict(frontmatter)
    result["body"] = body
    return result


def run(argv: list[str], env: dict[str, str] | None = None) -> int:
    """Parse ``argv`` and execute the matching command. Returns the process exit code."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    vault_root = default_vault_root(env=env)
    index_db = default_index_db(env=env)
    store = VaultStore(vault_root)
    embedder = load_embedder_from_env(env=env)

    try:
        if args.command == "put":
            try:
                knowledge_type = KnowledgeType.from_str(args.type)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            tags = [tag for tag in args.tags.split(",") if tag] if args.tags else []
            result = store.put(
                id=args.id,
                type=knowledge_type,
                title=args.title,
                body=args.body,
                scope=args.scope,
                tags=tags,
                ttl_days=args.ttl_days,
            )
            index = SqliteIndex(index_db, embedder=embedder)
            try:
                index.put(store.get(result.id))
            finally:
                index.close()
            print(json.dumps({"id": result.id, "created": result.created, "updated": result.updated}))
            return 0

        if args.command == "get":
            try:
                item = store.get(args.id)
            except NoteNotFoundError:
                print(f"note not found: {args.id}", file=sys.stderr)
                return 1
            print(json.dumps(_item_to_dict(item)))
            return 0

        if args.command == "list":
            knowledge_type = KnowledgeType.from_str(args.type) if args.type else None
            items = store.list(type=knowledge_type, tag=args.tag)
            print(json.dumps([{"id": item.id, "title": item.title} for item in items]))
            return 0

        if args.command == "search":
            index = SqliteIndex(index_db, embedder=embedder)
            try:
                ids = index.search(args.query, limit=args.limit)
            finally:
                index.close()
            results = []
            for note_id in ids:
                try:
                    item = store.get(note_id)
                    results.append({"id": item.id, "title": item.title})
                except NoteNotFoundError:
                    continue
            print(json.dumps({"results": results, "next_cursor": None}))
            return 0

        if args.command == "export":
            bundle = export_bundle(store)
            Path(args.output).write_text(json.dumps(bundle, indent=2), encoding="utf-8")
            print(json.dumps({"count": bundle["count"], "output": args.output}))
            return 0

        if args.command == "import":
            bundle = json.loads(Path(args.path).read_text(encoding="utf-8"))
            result = import_bundle(store, bundle, dry_run=args.dry_run)
            print(json.dumps({**result, "dry_run": args.dry_run}))
            return 0

        if args.command == "rebuild":
            index = SqliteIndex(index_db, embedder=embedder)
            try:
                index.rebuild(store.list())
            finally:
                index.close()
            print(json.dumps({"status": "ok"}))
            return 0

    except InvalidNoteIdError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # last resort — never a raw traceback for a CLI user
        print(f"secondmind: {exc}", file=sys.stderr)
        return 1

    print(f"unknown command: {args.command}", file=sys.stderr)
    return 2
