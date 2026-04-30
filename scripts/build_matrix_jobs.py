#!/usr/bin/env python3
"""
Walk every workloads/Rust/<crate>/etna.toml and emit a TSV of jobs to feed
into validate_faultloc_matrix.sh. One job per (workload, variant).

Output columns: workload\tproperty\tshort_name\tkind:arg\textra_features

Skips workloads with no src/bin/etna-faultloc.rs (un-ported).
Skips variants whose previous N=100 single-trial JSON didn't trigger (so we
don't waste an hour rebuilding a binary whose property never fails).
"""
import json, re, sys
from pathlib import Path

ROOT = Path("/Users/akeles/Programming/projects/PbtBenchmark/faultloc")
RESULTS = ROOT / "faultloc-results"
WORKLOADS = ROOT / "workloads" / "Rust"

EXTRA_FEATURES = {
    "arrayvec": "etna",
    "bytes": "etna",
    "crc32fast": "etna",
    "half": "faultloc",
    "hashbrown": "etna",
    "hex": "etna",
    "itertools": "etna",
    "nom-rs": "alloc",
    "rangemap": "etna",
    "smallvec": "etna",
    "tinyvec": "etna",
    "unicode-segmentation": "etna",
    "uuid": "v7",
}

def parse_tasks(toml_path):
    text = toml_path.read_text()
    blocks = re.split(r'\n\[\[tasks\]\]\s*\n', text)[1:]
    out = []
    for blk in blocks:
        short = re.search(r'short_name\s*=\s*"([^"]+)"', blk)
        prop  = re.search(r'property\s*=\s*"([^"]+)"', blk)
        kind  = re.search(r'kind\s*=\s*"(patch|marauders)"', blk)
        patch = re.search(r'patch\s*=\s*"([^"]+)"', blk)
        mut   = re.search(r'mutations\s*=\s*\["([^"]+)"\]', blk)
        if not (short and prop and kind):
            continue
        if kind.group(1) == "patch":
            arg = f"patch:{patch.group(1)}" if patch else f"patch:patches/{mut.group(1)}.patch"
        else:
            arg = f"marauders:{mut.group(1)}"
        out.append((short.group(1), prop.group(1), arg))
    return out

def previously_triggered(workload, short, mutation_id=None):
    """True if any prior result JSON for this variant has sample data.

    Older batches stored results under <mutation_id>/ rather than <short>/, and
    multi-trial batches saved per-trial JSONs. Sweep all of them.
    """
    candidate_dirs = [RESULTS / workload / short]
    if mutation_id:
        candidate_dirs.append(RESULTS / workload / mutation_id)
    for d in candidate_dirs:
        if not d.exists():
            continue
        for j in d.rglob("*.json"):
            if j.stat().st_size == 0:
                continue
            try:
                data = json.loads(j.read_text())
                if isinstance(data, dict):
                    if (data.get("positive_samples", 0) + data.get("negative_samples", 0)) > 0:
                        return True
            except Exception:
                continue
    return False

def main():
    jobs = []
    skipped = []
    for w_dir in sorted(WORKLOADS.iterdir()):
        if not w_dir.is_dir(): continue
        toml = w_dir / "etna.toml"
        bin_rs = w_dir / "src" / "bin" / "etna-faultloc.rs"
        if not toml.exists() or not bin_rs.exists():
            continue
        feats = EXTRA_FEATURES.get(w_dir.name, "")
        for short, prop, arg in parse_tasks(toml):
            mutation_id = arg.split(":", 1)[1].rsplit("/", 1)[-1].replace(".patch", "") if arg.startswith("patch:") else arg.split(":", 1)[1]
            if previously_triggered(w_dir.name, short, mutation_id):
                jobs.append((w_dir.name, prop, short, arg, feats))
            else:
                skipped.append((w_dir.name, short, "no prior trigger"))
    out_path = ROOT / "scripts" / "matrix_jobs.tsv"
    with open(out_path, "w") as f:
        f.write("workload\tproperty\tshort_name\tkind_arg\textra_features\n")
        for j in jobs:
            f.write("\t".join(j) + "\n")
    print(f"Wrote {len(jobs)} jobs to {out_path}")
    print(f"Skipped {len(skipped)} variants (no prior trigger):")
    for s in skipped[:15]:
        print(f"  - {s[0]}/{s[1]}")
    if len(skipped) > 15:
        print(f"  ... and {len(skipped) - 15} more")

if __name__ == "__main__":
    main()
