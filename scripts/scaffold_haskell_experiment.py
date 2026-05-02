#!/usr/bin/env python3
"""Scaffold steps.json + tests/<name>.json for every Haskell workload.

For each workload under workloads/Haskell/<name>/ that has an etna.toml
but is missing steps.json (or tests/<name>.json), generate the missing
file from the manifest. Idempotent — files already present are left
alone unless --force is passed.

This is the gluing step between an etna-ify run (which produces
workload artefacts) and `etna experiment run --tests <name>` (which
needs the step config + experiment manifest).
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

FAULTLOC = Path("/Users/akeles/Programming/projects/PbtBenchmark/faultloc")
HASKELL_DIR = FAULTLOC / "workloads" / "Haskell"
TESTS_DIR = FAULTLOC / "tests"

STEPS_JSON = {
    "setup_steps": [
        {
            "Command": {
                "command": "cabal",
                "args": ["build", "etna-runner", "--with-compiler=ghc-9.6.6"],
            }
        }
    ],
    "build_steps": [],
    "capabilities": {
        "solve": [
            {
                "Command": {
                    "command": "cabal",
                    "args": [
                        "run", "-v0",
                        "--with-compiler=ghc-9.6.6",
                        "etna-runner", "--",
                        "${strategy}", "${property}",
                    ],
                    "run_at": "${workload_path}",
                    "params": ["workload_path", "property", "strategy"],
                }
            }
        ]
    },
}


def write_steps(workload_dir: Path, force: bool) -> bool:
    p = workload_dir / "steps.json"
    if p.exists() and not force:
        return False
    p.write_text(json.dumps(STEPS_JSON, indent=2) + "\n")
    return True


def build_test_entries(manifest: dict, strategies: list[str]) -> list[dict]:
    entries = []
    workload_name = manifest["name"]
    for group in manifest.get("tasks", []):
        muts = group.get("mutations", [])
        if not muts:
            continue
        for mut in muts:
            for task in group.get("tasks", []):
                prop = task["property"]
                # Drop strategies the manifest declared as inapplicable for
                # this task. We honor `<strategy>_dropped = true` (full
                # exclusion) but still include `<strategy>_timeout = true`
                # entries — the runner will record the timeout as a
                # data point.
                tasks_for_mut = []
                for s in strategies:
                    if task.get(f"{s}_dropped") is True:
                        continue
                    tasks_for_mut.append({"strategy": s, "property": prop})
                entries.append({
                    "language": "Haskell",
                    "workload": workload_name,
                    "mode": "Solve",
                    "mutations": [mut],
                    "trials": 10,
                    "timeout": 600,
                    "tasks": tasks_for_mut,
                })
    return entries


def write_tests(workload_dir: Path, manifest: dict, force: bool) -> bool:
    name = manifest["name"]
    p = TESTS_DIR / f"{name}.json"
    if p.exists() and not force:
        return False
    strategies = manifest.get("strategies") or []
    if not strategies:
        return False
    entries = build_test_entries(manifest, strategies)
    p.write_text(json.dumps(entries, indent=2) + "\n")
    return True


def load_manifest(workload_dir: Path) -> dict | None:
    p = workload_dir / "etna.toml"
    if not p.exists():
        return None
    with p.open("rb") as f:
        return tomllib.load(f)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--force", action="store_true",
                    help="Overwrite existing steps.json / tests/<name>.json")
    ap.add_argument("--only", action="append", default=[],
                    help="Restrict to specific workload names; can repeat")
    args = ap.parse_args()

    if not HASKELL_DIR.is_dir():
        print(f"missing: {HASKELL_DIR}", file=sys.stderr)
        return 2
    TESTS_DIR.mkdir(exist_ok=True)

    skipped, scaffolded = 0, 0
    for d in sorted(HASKELL_DIR.iterdir()):
        if not d.is_dir():
            continue
        if args.only and d.name not in args.only:
            continue
        manifest = load_manifest(d)
        if manifest is None:
            print(f"  {d.name}: no etna.toml — skip")
            skipped += 1
            continue
        steps_done = write_steps(d, args.force)
        tests_done = write_tests(d, manifest, args.force)
        if steps_done or tests_done:
            scaffolded += 1
            tags = []
            if steps_done:
                tags.append("steps")
            if tests_done:
                tags.append(f"tests/{manifest['name']}.json")
            print(f"  {d.name}: wrote {', '.join(tags)}")
        else:
            print(f"  {d.name}: already scaffolded")
            skipped += 1

    print(f"---\nscaffolded: {scaffolded}  skipped: {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
