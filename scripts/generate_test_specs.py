#!/usr/bin/env python3
"""Generate tests/<name>.json and workloads/Rust/<name>/steps.json from each
workload's etna.toml (v2 schema with `[[tasks]]` + `[[tasks.tasks]]`).

Usage:
    scripts/generate_test_specs.py <workload> [<workload> ...]
    scripts/generate_test_specs.py --all   # every dir under workloads/Rust with etna.toml

Each `[[tasks]]` block in etna.toml is one mutation; each `[[tasks.tasks]]`
inside is one property under that mutation. Default frameworks are the four
runners (proptest, quickcheck, crabcheck, hegel); override with
`frameworks = [...]` on either the outer task or the inner property.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_FRAMEWORKS = ["proptest", "quickcheck", "crabcheck", "hegel"]
DEFAULT_TRIALS = 10
DEFAULT_TIMEOUT = 600

def _build_args(wl_root: Path) -> list[str]:
    """Cargo workspaces with a root package + sibling etna_runner crate
    (e.g. regex-syntax, toml_edit) need an explicit `--package etna_runner`,
    because `--bin etna` looks only in default-run packages and the root
    package doesn't contain the etna binary. Workspace-only roots (rstar,
    chrono, lru, …) accept the bare `--bin etna`."""
    base = ["build", "--release", "--bin", "etna"]
    cargo_toml = wl_root / "Cargo.toml"
    runner_toml = wl_root / "etna_runner" / "Cargo.toml"
    if cargo_toml.exists() and runner_toml.exists():
        text = cargo_toml.read_text()
        # Heuristic: a `[package]` section AND a `[workspace]` section means
        # the bare `--bin etna` would resolve against the root package.
        if "\n[package]" in ("\n" + text) and "\n[workspace]" in ("\n" + text):
            return base + ["--package", "etna_runner"]
    return base


def steps_json_for(wl_root: Path) -> dict:
    return {
        "setup_steps": [],
        "build_steps": [
            {
                "Command": {
                    "command": "cargo",
                    "args": _build_args(wl_root),
                    "run_at": "${workload_path}",
                }
            }
        ],
        "capabilities": {
            "solve": [
                {
                    "Command": {
                        "command": "${workload_path}/target/release/etna",
                        "args": ["${strategy}", "${property}"],
                        "params": ["workload_path", "property", "strategy"],
                    }
                }
            ]
        },
    }


def generate_for(workload: str) -> tuple[int, int]:
    wl_root = ROOT / "workloads" / "Rust" / workload
    etna_toml = wl_root / "etna.toml"
    if not etna_toml.exists():
        raise SystemExit(f"{workload}: missing {etna_toml}")

    with etna_toml.open("rb") as f:
        cfg = tomllib.load(f)

    blocks = cfg.get("tasks", [])
    if not blocks:
        raise SystemExit(f"{workload}: no [[tasks]] in {etna_toml}")

    entries = []
    task_total = 0
    for block in blocks:
        mutations = block.get("mutations")
        if not mutations:
            raise SystemExit(f"{workload}: [[tasks]] block missing 'mutations'")
        outer_fws = block.get("frameworks", DEFAULT_FRAMEWORKS)
        inner_props = block.get("tasks", [])
        if not inner_props:
            raise SystemExit(
                f"{workload}: [[tasks]] for {mutations} has no [[tasks.tasks]]"
            )
        tasks_json = []
        for inner in inner_props:
            prop = inner.get("property")
            if not prop:
                raise SystemExit(
                    f"{workload}: [[tasks.tasks]] in {mutations} missing 'property'"
                )
            fws = inner.get("frameworks", outer_fws)
            for fw in fws:
                tasks_json.append({"strategy": fw, "property": prop})
        entries.append(
            {
                "language": "Rust",
                "workload": workload,
                "mode": "Solve",
                "mutations": mutations,
                "trials": DEFAULT_TRIALS,
                "timeout": DEFAULT_TIMEOUT,
                "tasks": tasks_json,
            }
        )
        task_total += len(tasks_json)

    tests_path = ROOT / "tests" / f"{workload}.json"
    tests_path.write_text(json.dumps(entries, indent=2) + "\n")

    steps_path = wl_root / "steps.json"
    steps_path.write_text(json.dumps(steps_json_for(wl_root), indent=2) + "\n")

    return len(entries), task_total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workloads", nargs="*", help="workload names under workloads/Rust/")
    parser.add_argument("--all", action="store_true", help="every dir with etna.toml")
    args = parser.parse_args()

    if args.all:
        names = sorted(
            p.parent.name
            for p in (ROOT / "workloads" / "Rust").glob("*/etna.toml")
        )
    else:
        names = args.workloads

    if not names:
        parser.error("provide workload names or --all")

    total_e = 0
    total_t = 0
    for wl in names:
        e, t = generate_for(wl)
        print(f"  {wl:<25}  entries={e}  tasks={t}")
        total_e += e
        total_t += t
    print(f"\n  TOTAL                      entries={total_e}  tasks={total_t}")


if __name__ == "__main__":
    main()
