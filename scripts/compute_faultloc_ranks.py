#!/usr/bin/env python3
"""
Compute fault-localization rank for every variant that has a single-trial JSON.

Ground truth per variant is extracted from the patch file (or the marauders
marker line). Rank is computed by 5 SBFL metrics + delta.
"""
import json, re, sys
from pathlib import Path

ROOT = Path("/Users/akeles/Programming/projects/PbtBenchmark/faultloc")
RESULTS = ROOT / "faultloc-results"
WORKLOADS = ROOT / "workloads" / "Rust"

def parse_patch_truth(patch_path):
    """Return list of (file, start_line, end_line) per hunk from a .patch file."""
    out = []
    cur_file = None
    text = patch_path.read_text()
    for line in text.splitlines():
        m = re.match(r'^\+\+\+ b/(.+)$', line)
        if m:
            cur_file = m.group(1)
            continue
        m = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
        if m and cur_file:
            start = int(m.group(3))
            span = int(m.group(4) or 1)
            out.append((cur_file, start, start + max(span - 1, 0)))
    return out

def parse_etna_tasks(toml_path):
    """Return list of dicts per task. Each: {short, kind, patch, truth_file, truth_line_from_toml, mutations}."""
    text = toml_path.read_text()
    blocks = re.split(r'\n\[\[tasks\]\]\s*\n', text)[1:]
    out = []
    for blk in blocks:
        short = re.search(r'short_name\s*=\s*"([^"]+)"', blk)
        kind  = re.search(r'kind\s*=\s*"(patch|marauders)"', blk)
        patch = re.search(r'patch\s*=\s*"([^"]+)"', blk)
        loc_file = re.search(r'locations\s*=\s*\[\{\s*file\s*=\s*"([^"]+)"', blk)
        loc_line = re.search(r'line\s*=\s*(\d+)', blk)
        mut   = re.search(r'mutations\s*=\s*\["([^"]+)"\]', blk)
        if not short: continue
        out.append({
            "short": short.group(1),
            "kind": kind.group(1) if kind else None,
            "patch_rel": patch.group(1) if patch else None,
            "loc_file": loc_file.group(1) if loc_file else None,
            "loc_line": int(loc_line.group(1)) if loc_line else None,
            "mutation_id": mut.group(1) if mut else None,
        })
    return out

def resolve_truth(wdir, task):
    """Return list of (file, start, end) hunks that are ground truth."""
    truths = []
    if task["patch_rel"]:
        patch_path = wdir / task["patch_rel"]
        if patch_path.exists():
            truths = parse_patch_truth(patch_path)
    if not truths and task["loc_file"] and task["loc_line"] is not None:
        # Marauders markers: the etna.toml line points at the `/*| name */`
        # comment line. The actual live code line is +1; the replacement block
        # extends through +6 typically (the `/*|| id */ … /*|` frame). Widen
        # the truth range to ±8 lines to cover both.
        ln = task["loc_line"]
        if task["kind"] == "marauders":
            truths = [(task["loc_file"], max(ln - 2, 1), ln + 10)]
        else:
            truths = [(task["loc_file"], ln, ln)]
    return truths

def sbfl_key(region, metric):
    if metric == "delta":
        return region.get("delta", 0.0)
    return region.get("suspiciousness", {}).get(metric, 0.0)

def region_matches(region, truths):
    rf = region.get("file", "")
    sl = region.get("start_line", -1)
    el = region.get("end_line", -1)
    for (tf, ts, te) in truths:
        if rf.endswith(tf) and not (el < ts or sl > te):
            return True
    return False

def rank_by(regions, truths, metric):
    sorted_r = sorted(regions, key=lambda r: -sbfl_key(r, metric))
    for rank, r in enumerate(sorted_r, start=1):
        if region_matches(r, truths):
            return rank
    return None

def aggregate_functions(regions):
    """Group regions by (file, function); take max metric value per function."""
    groups = {}
    for r in regions:
        key = (r.get("file", ""), r.get("function", ""))
        if key not in groups:
            groups[key] = dict(r)
            groups[key]["_regions"] = [r]
        else:
            g = groups[key]
            g["_regions"].append(r)
            # Keep max values for suspiciousness + delta + widest line range
            for metric in ["tarantula", "ochiai", "dstar", "jaccard", "op2"]:
                cur = g.get("suspiciousness", {}).get(metric, 0.0)
                new = r.get("suspiciousness", {}).get(metric, 0.0)
                if new > cur:
                    g.setdefault("suspiciousness", {})[metric] = new
            if r.get("delta", 0.0) > g.get("delta", 0.0):
                g["delta"] = r["delta"]
            g["start_line"] = min(g["start_line"], r["start_line"])
            g["end_line"] = max(g["end_line"], r["end_line"])
    return list(groups.values())

def rank_by_function(regions, truths, metric):
    grouped = aggregate_functions(regions)
    return rank_by(grouped, truths, metric)

def main():
    rows = []
    for w_dir in sorted(WORKLOADS.iterdir()):
        if not w_dir.is_dir(): continue
        toml = w_dir / "etna.toml"
        if not toml.exists(): continue
        for task in parse_etna_tasks(toml):
            short = task["short"]
            truths = resolve_truth(w_dir, task)
            # Try short_name dir; fall back to mutation_id dir (older naming).
            result_json = RESULTS / w_dir.name / short / "single-trial-N100.json"
            if not result_json.exists() and task["mutation_id"]:
                result_json = RESULTS / w_dir.name / task["mutation_id"] / "single-trial-N100.json"
            row = {
                "workload": w_dir.name,
                "variant": short,
                "kind": task["kind"],
                "truth_hunks": len(truths),
                "truth_preview": f"{truths[0][0]}:{truths[0][1]}-{truths[0][2]}" if truths else "NO_TRUTH",
            }
            if not result_json.exists() or result_json.stat().st_size == 0:
                row["status"] = "no-data"
                rows.append(row); continue
            try:
                data = json.loads(result_json.read_text())
            except Exception as e:
                row["status"] = f"parse-err"; rows.append(row); continue
            regions = data.get("regions", [])
            row["n_regions"] = len(regions)
            row["pos"] = data.get("positive_samples", 0)
            row["neg"] = data.get("negative_samples", 0)
            row["status"] = "ok"
            if truths:
                for metric in ["ochiai", "tarantula", "dstar", "jaccard", "op2", "delta"]:
                    row[metric] = rank_by(regions, truths, metric)
                    row[f"{metric}_fn"] = rank_by_function(regions, truths, metric)
            rows.append(row)
    # Per-workload breakdown
    total = len(rows)
    with_data = [r for r in rows if r.get("status") == "ok"]
    with_truth = [r for r in with_data if r.get("truth_hunks", 0) > 0]
    found_ochiai = [r for r in with_truth if r.get("ochiai") is not None]

    print(f"Total variants parsed from etna.toml: {total}")
    print(f"  With single-trial JSON data:         {len(with_data)}")
    print(f"  With extractable ground truth:       {len(with_truth)}")
    print(f"  Buggy region found in top-N list:    {len(found_ochiai)} (ochiai)")
    print()
    denom = len(with_truth) or 1
    def print_table(title, key_suffix=""):
        print(title)
        print(f"{'metric':<12} {'top-1':>8} {'top-5':>8} {'top-10':>8} {'top-20':>8} {'top-50':>8} {'top-100':>8} {'MRR':>8} {'median':>8}")
        for metric in ["ochiai", "tarantula", "dstar", "jaccard", "op2", "delta"]:
            key = metric + key_suffix
            ranks = [r[key] for r in with_truth if r.get(key) is not None]
            if not ranks: continue
            top1  = sum(1 for x in ranks if x <=   1) / denom * 100
            top5  = sum(1 for x in ranks if x <=   5) / denom * 100
            top10 = sum(1 for x in ranks if x <=  10) / denom * 100
            top20 = sum(1 for x in ranks if x <=  20) / denom * 100
            top50 = sum(1 for x in ranks if x <=  50) / denom * 100
            top100= sum(1 for x in ranks if x <= 100) / denom * 100
            mrr   = sum(1/x for x in ranks) / denom
            median = sorted(ranks)[len(ranks)//2]
            print(f"{metric:<12} {top1:>7.1f}% {top5:>7.1f}% {top10:>7.1f}% {top20:>7.1f}% {top50:>7.1f}% {top100:>7.1f}% {mrr:>7.3f} {median:>8}")

    print_table("Per-REGION ranking (LLVM basic-block granularity):")
    print()
    print_table("Per-FUNCTION ranking (aggregate max metric across same-function regions):", key_suffix="_fn")
    print()
    print(f"Denominator = {denom} variants with JSON + ground truth.")
    print(f"  \"Not found\" (bug region absent from JSON regions): {denom - len(found_ochiai)}")
    print()
    # Save
    out_path = RESULTS / "per_variant_ranks.jsonl"
    with open(out_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"Wrote per-variant ranks to {out_path}")

if __name__ == "__main__":
    main()
