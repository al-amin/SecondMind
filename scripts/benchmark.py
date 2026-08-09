"""Performance benchmark harness for SecondMind — measured, never claimed.

Seeds a synthetic vault and reports (not asserts, to avoid CI flakiness)
put latency, search latency, full-rebuild time, and export/import time at
1,000 and 10,000 notes, per SPEC.md §8. Run with:

    python3 scripts/benchmark.py

Uses only stdlib (time.perf_counter, tempfile) — no pytest-benchmark
dependency, consistent with the zero-install core.
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from secondmind.models import KnowledgeType  # noqa: E402
from secondmind.portability import export_bundle, import_bundle  # noqa: E402
from secondmind.sqlite_index import SqliteIndex  # noqa: E402
from secondmind.store import VaultStore  # noqa: E402

_WORDS = [
    "system", "design", "memory", "search", "vault", "index", "note", "agent",
    "protocol", "client", "server", "async", "python", "database", "network",
    "cache", "session", "token", "model", "vector", "hybrid", "rank", "fusion",
]


def _synthetic_body(i: int) -> str:
    return " ".join(_WORDS[(i + offset) % len(_WORDS)] for offset in range(20))


def _percentile(samples: list[float], pct: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = min(int(len(ordered) * pct), len(ordered) - 1)
    return ordered[index]


def _measure(fn) -> float:
    start = time.perf_counter()
    fn()
    return (time.perf_counter() - start) * 1000  # milliseconds


def run_benchmark(note_count: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        vault_root = Path(tmp) / "vault"
        db_path = Path(tmp) / "index.db"
        store = VaultStore(vault_root)
        index = SqliteIndex(db_path)

        put_latencies: list[float] = []
        for i in range(note_count):
            body = _synthetic_body(i)

            def do_put() -> None:
                store.put(id=f"note-{i}", type=KnowledgeType.SEMANTIC, title=f"Note {i}", body=body)

            put_latencies.append(_measure(do_put))
            index.put(store.get(f"note-{i}"))

        search_latencies: list[float] = []
        for word in _WORDS[:20]:

            def do_search() -> None:
                index.search(word, limit=20)

            search_latencies.append(_measure(do_search))

        rebuild_ms = _measure(lambda: index.rebuild(store.list()))

        bundle_holder: dict[str, object] = {}

        def do_export() -> None:
            bundle_holder["bundle"] = export_bundle(store)

        export_ms = _measure(do_export)

        fresh_store = VaultStore(Path(tmp) / "fresh-vault")
        import_ms = _measure(lambda: import_bundle(fresh_store, bundle_holder["bundle"]))

        index.close()

        return {
            "note_count": note_count,
            "put_p50_ms": round(_percentile(put_latencies, 0.50), 3),
            "put_p95_ms": round(_percentile(put_latencies, 0.95), 3),
            "search_p50_ms": round(_percentile(search_latencies, 0.50), 3),
            "search_p95_ms": round(_percentile(search_latencies, 0.95), 3),
            "rebuild_ms": round(rebuild_ms, 3),
            "export_ms": round(export_ms, 3),
            "import_ms": round(import_ms, 3),
        }


def main() -> None:
    print("SecondMind Performance Benchmark")
    print("=" * 60)
    for note_count in (1_000, 10_000):
        print(f"\nSeeding {note_count} notes...")
        result = run_benchmark(note_count)
        for key, value in result.items():
            print(f"  {key}: {value}")
        target_note = ""
        if note_count == 10_000 and result["search_p95_ms"] > 50:
            target_note = "  (target: sub-50ms p95 search at 10,000 notes — MISSED, reporting honestly)"
        elif note_count == 10_000:
            target_note = "  (target: sub-50ms p95 search at 10,000 notes — met)"
        if target_note:
            print(target_note)


if __name__ == "__main__":
    main()
