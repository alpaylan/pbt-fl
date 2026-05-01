#!/usr/bin/env python3
"""Generate tests/<workload>.json from a Python workload's etna.toml.

Schema mirrors the Rust test files (e.g. tests/strsim.json):
  one JSON object per [[tasks]] group, with `tasks` expanded to the
  (property × strategy) cross product. Strategies are "hypothesis" and
  "crosshair" — the two backends the Python pipeline supports.

Usage:
    python scripts/gen_python_tests.py <workload_dir> [<workload_dir> ...]
    python scripts/gen_python_tests.py --all       # every workloads/Python/*

Writes tests/<workload>.json relative to the faultloc repo root.
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

FAULTLOC = Path(__file__).resolve().parent.parent
TESTS_DIR = FAULTLOC / "tests"
DEFAULT_TRIALS = 10
DEFAULT_TIMEOUT = 600
STRATEGIES = ["hypothesis", "crosshair"]


def gen_one(workload_dir: Path) -> Path:
    manifest_path = workload_dir / "etna.toml"
    if not manifest_path.exists():
        raise SystemExit(f"error: {manifest_path} not found")
    with manifest_path.open("rb") as f:
        manifest = tomllib.load(f)

    name = manifest.get("name") or workload_dir.name
    if manifest.get("language") != "python":
        raise SystemExit(
            f"error: {manifest_path}: language must be 'python', "
            f"got {manifest.get('language')!r}"
        )

    entries: list[dict] = []
    for group in manifest.get("tasks", []):
        mutations = list(group.get("mutations", []))
        tasks_block = group.get("tasks", [])
        cross: list[dict] = []
        for t in tasks_block:
            prop = t.get("property")
            if not prop:
                continue
            for strat in STRATEGIES:
                cross.append({"strategy": strat, "property": prop})
        if not cross:
            print(f"warning: {workload_dir.name}: variant {mutations} has no "
                  f"tasks, skipping", file=sys.stderr)
            continue
        entries.append({
            "language": "Python",
            "workload": name,
            "mode": "Solve",
            "mutations": mutations,
            "trials": DEFAULT_TRIALS,
            "timeout": DEFAULT_TIMEOUT,
            "tasks": cross,
        })

    out = TESTS_DIR / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(entries, indent=2) + "\n")
    print(f"{out.relative_to(FAULTLOC)}: {len(entries)} variant(s), "
          f"{sum(len(e['tasks']) for e in entries)} task(s)")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("workloads", nargs="*", help="Workload directories")
    p.add_argument("--all", action="store_true",
                   help="Process every workloads/Python/<dir>")
    args = p.parse_args()

    if args.all:
        roots = sorted(
            d for d in (FAULTLOC / "workloads" / "Python").iterdir()
            if d.is_dir() and (d / "etna.toml").exists()
        )
    else:
        roots = [Path(w).resolve() for w in args.workloads]
    if not roots:
        p.error("no workloads given (pass paths or --all)")

    for w in roots:
        gen_one(w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
