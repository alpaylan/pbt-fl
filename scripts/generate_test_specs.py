#!/usr/bin/env python3
"""Generate tests/<name>.json and workloads/Rust/<name>/steps.json for overnight
pi-etna workloads.

Reads each workload's etna.toml plus its src/bin/etna.rs dispatcher, builds the
snake_case property -> PascalCase-dispatch-name map by scanning match arms, and
emits one test-selector entry per variant for every declared framework.
"""
from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path("/Users/akeles/Programming/projects/PbtBenchmark/faultloc")
WORKLOADS = [
    "unicode-segmentation",
    "bitvec-rs",
    "rust-csv",
    "nom-rs",
    "arroy",
    "buf-list",
    "roaring-rs",
    "regex",
]

STEPS_JSON = {
    "setup_steps": [],
    "build_steps": [
        {
            "Command": {
                "command": "cargo",
                "args": ["build", "--release", "--bin", "etna"],
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

ARM_RE = re.compile(r'"([A-Z][A-Za-z0-9]+)"\s*=>')
PROP_CALL_RE = re.compile(r"\bproperty_([a-z0-9_]+)\b")


def find_etna_rs(workload_root: Path) -> Path:
    """Standard layout is src/bin/etna.rs; workspaces (e.g. roaring-rs) nest it
    under a member crate."""
    for candidate in [
        workload_root / "src" / "bin" / "etna.rs",
        *workload_root.glob("*/src/bin/etna.rs"),
    ]:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"no src/bin/etna.rs under {workload_root}")


def build_snake_to_pascal(etna_rs: Path) -> dict[str, str]:
    """Walk `"PascalCase" =>` arms and record the first property_<snake> call in
    each arm body. First occurrence wins, so later duplicates (e.g. a sub-match
    inside the arm) don't clobber the canonical mapping."""
    src = etna_rs.read_text()
    arms = [(m.start(), m.end(), m.group(1)) for m in ARM_RE.finditer(src)]
    mapping: dict[str, str] = {}
    for i, (_, end, pascal) in enumerate(arms):
        block_end = arms[i + 1][0] if i + 1 < len(arms) else len(src)
        body = src[end:block_end]
        call = PROP_CALL_RE.search(body)
        if not call:
            continue
        snake = call.group(1)
        mapping.setdefault(snake, pascal)
    return mapping


def generate_for(workload: str) -> tuple[int, int]:
    """Returns (variant_count, task_count) written."""
    wl_root = ROOT / "workloads" / "Rust" / workload
    etna_toml = wl_root / "etna.toml"
    etna_rs = find_etna_rs(wl_root)

    with etna_toml.open("rb") as f:
        cfg = tomllib.load(f)

    mapping = build_snake_to_pascal(etna_rs)
    variants = cfg.get("variant", [])
    entries = []
    task_total = 0
    for v in variants:
        snake = v["property"]
        if snake not in mapping:
            raise SystemExit(
                f"{workload}: variant {v['name']!r} references property "
                f"{snake!r} but no dispatch arm in {etna_rs} calls "
                f"property_{snake} (known: {sorted(mapping)})"
            )
        pascal = mapping[snake]
        frameworks = v.get("frameworks", ["proptest", "quickcheck", "crabcheck", "hegel"])
        entries.append({
            "language": "Rust",
            "workload": workload,
            "mode": "Solve",
            "mutations": [v["name"]],
            "trials": 1,
            "timeout": 600,
            "tasks": [{"strategy": fw, "property": pascal} for fw in frameworks],
        })
        task_total += len(frameworks)

    tests_path = ROOT / "tests" / f"{workload}.json"
    tests_path.write_text(json.dumps(entries, indent=2) + "\n")

    steps_path = wl_root / "steps.json"
    steps_path.write_text(json.dumps(STEPS_JSON, indent=2) + "\n")

    return len(variants), task_total


def main() -> None:
    total_v = 0
    total_t = 0
    for wl in WORKLOADS:
        v, t = generate_for(wl)
        print(f"  {wl:<22}  variants={v}  tasks={t}")
        total_v += v
        total_t += t
    print(f"\n  TOTAL                   variants={total_v}  tasks={total_t}")


if __name__ == "__main__":
    main()
