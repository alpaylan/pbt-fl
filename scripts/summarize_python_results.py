#!/usr/bin/env python3
"""Summarize the latest Python experiment results from store.jsonl.

Reads /Users/akeles/Programming/projects/PbtBenchmark/faultloc/store.jsonl and
aggregates rows where language=python by (workload, strategy, status).
Prints a per-workload table plus a totals row. Useful after running
`etna experiment run --tests <name>` for a batch of Python workloads.

Default scope: every record in store.jsonl with language=python. Pass
--since YYYY-MM-DD to restrict to recent runs.

Usage:
    python scripts/summarize_python_results.py
    python scripts/summarize_python_results.py --since 2026-05-01
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

FAULTLOC = Path(__file__).resolve().parent.parent
STORE = FAULTLOC / "store.jsonl"

STATUSES = ("passed", "failed", "aborted")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--since", help="ISO date floor (e.g. 2026-05-01)")
    p.add_argument("--store", default=str(STORE),
                   help=f"Path to store.jsonl (default: {STORE})")
    args = p.parse_args()

    since = args.since
    # buckets[workload][strategy][status] = count
    buckets: dict[str, dict[str, dict[str, int]]] = \
        defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    sample_cex: dict[tuple[str, str, str], str] = {}

    with open(args.store) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            d = rec.get("data", {})
            if d.get("language") != "python":
                continue
            if since and d.get("timestamp", "")[:10] < since:
                continue
            wl = d.get("workload", "?")
            strat = d.get("strategy", "?")
            status = d.get("status", "?")
            buckets[wl][strat][status] += 1
            if status == "failed":
                key = (wl, strat, d.get("property", "?"))
                if key not in sample_cex and d.get("counterexample"):
                    sample_cex[key] = d["counterexample"]

    if not buckets:
        print("(no Python results in store.jsonl)")
        return 0

    print(f"{'workload':<22} {'strategy':<11} {'pass':>5} {'fail':>5} {'abort':>5}")
    print("-" * 56)
    grand: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for wl in sorted(buckets):
        for strat in sorted(buckets[wl]):
            counts = buckets[wl][strat]
            print(f"{wl:<22} {strat:<11} "
                  f"{counts.get('passed', 0):>5} "
                  f"{counts.get('failed', 0):>5} "
                  f"{counts.get('aborted', 0):>5}")
            for s in STATUSES:
                grand[strat][s] += counts.get(s, 0)
    print("-" * 56)
    for strat in sorted(grand):
        print(f"{'TOTAL':<22} {strat:<11} "
              f"{grand[strat].get('passed', 0):>5} "
              f"{grand[strat].get('failed', 0):>5} "
              f"{grand[strat].get('aborted', 0):>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
