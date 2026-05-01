#!/usr/bin/env python3
"""Write `steps.json` into every Python workload so etna can discover and
run it. Etna's `experiment::workload_path` walks `workloads/` recursively
and identifies a directory as a workload by the presence of `steps.json`
(see etna2/src/experiment.rs:42).

Schema mirrors the Lean (Cedar) steps.json — patch-kind variants are
activated by `marauders::set_variant` driven directly off `patches/*.patch`,
so no per-step `git apply` is needed. Just declare:

  * setup_steps: `uv sync` inside etna/ to materialize the venv
  * build_steps: empty (pure python — no compile)
  * capabilities.solve: invoke the runner via `uv run etna-runner`,
    passing ${strategy} and ${property} from the test JSON.

Usage:
    python scripts/gen_python_steps.py <workload_dir> [<workload_dir> ...]
    python scripts/gen_python_steps.py --all
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

FAULTLOC = Path(__file__).resolve().parent.parent

STEPS_JSON = {
    "setup_steps": [
        # etna's `build()` overrides current_dir to the workload root, so
        # `run_at` is ignored for setup/build steps. Wrap in bash -c so the
        # cd is encoded in the command — matches the Cedar / Lean pattern.
        {
            "Command": {
                "command": "bash",
                "args": ["-c", "cd etna && uv sync"],
            }
        }
    ],
    "build_steps": [],
    "capabilities": {
        "solve": [
            # Run-step `run_at` IS respected (different code path), so the
            # solve command can use it directly.
            {
                "Command": {
                    "command": "uv",
                    "args": [
                        "run",
                        "etna-runner",
                        "${strategy}",
                        "${property}",
                    ],
                    "run_at": "${workload_path}/etna",
                    "params": ["workload_path", "property", "strategy"],
                }
            }
        ]
    },
}


def gen_one(workload_dir: Path) -> Path:
    manifest_path = workload_dir / "etna.toml"
    if not manifest_path.exists():
        raise SystemExit(f"error: {manifest_path} not found")
    with manifest_path.open("rb") as f:
        manifest = tomllib.load(f)
    if manifest.get("language") != "python":
        raise SystemExit(
            f"error: {manifest_path}: language must be 'python', "
            f"got {manifest.get('language')!r}"
        )
    out = workload_dir / "steps.json"
    out.write_text(json.dumps(STEPS_JSON, indent=2) + "\n")
    print(f"{out.relative_to(FAULTLOC)} written")
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
