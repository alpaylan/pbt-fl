#!/usr/bin/env python3
"""
Batch existential-subset search across a stratified sample of variants where
matrix ochiai_fn > 10.

For each variant in the sample:
  1. apply patch, rebuild with coverage, run with N=100
  2. extract per-snapshot count matrix via llvm-cov export
  3. greedy + 2 random-restart subset reductions for ochiai and delta
  4. record (workload, variant, tier, baseline_rank, best_subset_rank,
     n_pos, n_neg) for each metric
  5. revert patch + wipe coverage

Output: faultloc-results/existential_results.jsonl
"""
import json, math, random, statistics, subprocess, sys, time
from collections import defaultdict
from pathlib import Path
import re, os

ROOT = Path("/Users/akeles/Programming/projects/PbtBenchmark/faultloc")
RESULTS_FILE = ROOT / "faultloc-results" / "existential_results.jsonl"
LOG_FILE = ROOT / "scripts" / "log" / "batch_existential.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

# ---------- helpers (subset of plan_c_analyze + existential_subset) ----------
def parse_patch_truth(patch_path):
    out = []; cur_file = None
    for line in patch_path.read_text().splitlines():
        m = re.match(r'^\+\+\+ b/(.+)$', line)
        if m: cur_file = m.group(1); continue
        m = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
        if m and cur_file:
            start = int(m.group(3))
            span = int(m.group(4) or 1)
            out.append((cur_file, start, start + max(span - 1, 0)))
    return out

def parse_etna_tasks(toml_path):
    text = toml_path.read_text()
    blocks = re.split(r'\n\[\[tasks\]\]\s*\n', text)[1:]
    out = []
    for blk in blocks:
        short = re.search(r'short_name\s*=\s*"([^"]+)"', blk)
        prop = re.search(r'property\s*=\s*"([^"]+)"', blk)
        kind = re.search(r'kind\s*=\s*"(patch|marauders)"', blk)
        patch = re.search(r'patch\s*=\s*"([^"]+)"', blk)
        mut  = re.search(r'mutations\s*=\s*\["([^"]+)"\]', blk)
        if not short: continue
        out.append({"short": short.group(1), "property": prop.group(1) if prop else None,
                    "kind": kind.group(1) if kind else None,
                    "patch_rel": patch.group(1) if patch else None,
                    "mutation_id": mut.group(1) if mut else None})
    return out

EXTRA_FEATURES = {
    "arrayvec":"etna","bytes":"etna","crc32fast":"etna","half":"faultloc",
    "hashbrown":"etna","hex":"etna","itertools":"etna","nom-rs":"alloc",
    "rangemap":"etna","smallvec":"etna","tinyvec":"etna",
    "unicode-segmentation":"etna","uuid":"v7",
}

WORKLOAD_MODULE = {
    "rust-base64":"base","rust-csv":"csv","rust-decimal":"rust_decimal",
    "fast-float2":"fast_float","im-rs":"im","nom-rs":"nom",
    "ordered-float":"ordered_float","unicode-segmentation":"unicode_segmentation",
    "buf-list":"buf_list","bitvec-rs":"bitvec",
    # rest map directly with hyphens → underscores or identical
}
def module_for(workload):
    if workload in WORKLOAD_MODULE: return WORKLOAD_MODULE[workload]
    return workload.replace("-", "_")

def log(msg):
    print(msg, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

def run(cmd, cwd=None, check=True, timeout=900):
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True, timeout=timeout)

# ---------- truth derivation ----------
def truth_for_variant(workload, short):
    wdir = ROOT / "workloads" / "Rust" / workload
    toml = wdir / "etna.toml"
    if not toml.exists(): return None, None
    for task in parse_etna_tasks(toml):
        if task["short"] != short: continue
        if task["kind"] == "patch" and task["patch_rel"]:
            patch = wdir / task["patch_rel"]
            if patch.exists():
                hunks = parse_patch_truth(patch)
                if hunks: return hunks, task
        # marauders — fall back to file:line from etna.toml (skipped for batch)
        return None, task
    return None, None

# ---------- workload run (apply patch, rebuild, run N=100) ----------
def prepare_variant(workload, task):
    wdir = ROOT / "workloads" / "Rust" / workload
    if task["kind"] == "patch":
        patch = task["patch_rel"]
        # try ignore-whitespace then -C0
        for opts in [["--ignore-whitespace"], ["--ignore-whitespace", "-C0"]]:
            r = subprocess.run(["git","apply",*opts,patch], cwd=wdir, capture_output=True, text=True)
            if r.returncode == 0: break
        else:
            return False
    else:
        # marauders — skipped for now
        return False
    return True

def revert_variant(workload, task):
    wdir = ROOT / "workloads" / "Rust" / workload
    if task["kind"] == "patch":
        patch = task["patch_rel"]
        for opts in [["--ignore-whitespace"], ["--ignore-whitespace", "-C0"]]:
            r = subprocess.run(["git","apply","-R",*opts,patch], cwd=wdir, capture_output=True, text=True)
            if r.returncode == 0: return

def rebuild_and_run(workload, task):
    wdir = ROOT / "workloads" / "Rust" / workload
    feat = EXTRA_FEATURES.get(workload, "")
    feat_args = ["--features", feat] if feat else []
    env = os.environ.copy()
    env["CARGO_INCREMENTAL"] = "1"  # incremental ok for existential batch
    env["RUSTFLAGS"] = "-C instrument-coverage -C link-dead-code -C codegen-units=1 -C inline-threshold=0 -C llvm-args=-inline-threshold=0 -C debuginfo=2"
    log(f"  building {workload}/{task['short']} ...")
    r = subprocess.run(["cargo","build","--release","--bin","etna-faultloc",*feat_args],
                       cwd=wdir, capture_output=True, text=True, env=env, timeout=900)
    if r.returncode != 0:
        log(f"  BUILD FAILED: {r.stderr[-300:]}")
        return False
    # wipe + run
    for d in ["coverage","profdata","jsondata"]:
        sub = wdir / d
        if sub.exists(): subprocess.run(["rm","-rf",str(sub)])
    (wdir/"coverage").mkdir(exist_ok=True)
    env2 = os.environ.copy()
    env2["CRABCHECK_PROFILING_MUTATIONS"] = "100"
    env2["LLVM_PROFILE_FILE"] = "coverage/snapshot_%p-%m.profraw"
    log(f"  running etna-faultloc crabcheck {task['property']} ...")
    r = subprocess.run([str(wdir/"target/release/etna-faultloc"),"crabcheck",task["property"]],
                       cwd=wdir, capture_output=True, text=True, env=env2, timeout=600)
    # fast-analyze to materialize indices.json
    module = module_for(workload)
    r = subprocess.run(["crabcheck-profiling-fast-analyze","coverage",module,
                        str(wdir/"target/release/etna-faultloc"),"--print-json"],
                       cwd=wdir, capture_output=True, text=True, timeout=600)
    return (wdir/"coverage/indices.json").exists()

def cleanup_variant(workload, task):
    wdir = ROOT / "workloads" / "Rust" / workload
    for d in ["coverage","profdata","jsondata"]:
        sub = wdir / d
        if sub.exists(): subprocess.run(["rm","-rf",str(sub)])
    revert_variant(workload, task)

# ---------- count matrix + existential search ----------
def load_count_matrix(wdir, module, truth_hunks):
    indices = json.loads((wdir/"coverage/indices.json").read_text())
    all_pos = sorted(indices["positives"])
    all_neg = sorted(indices["negatives"])
    counts = defaultdict(dict)
    truth_keys = set()
    bin_path = wdir/"target/release/etna-faultloc"
    pd_dir = wdir/"profdata"
    for s in sorted(set(all_pos)|set(all_neg)):
        pd = pd_dir / f"snapshot_iteration_{s}.profdata"
        if not pd.exists(): continue
        cov = json.loads(subprocess.run(
            ["llvm-cov","export",str(bin_path),f"--instr-profile={pd}","--format=text","--skip-expansions"],
            capture_output=True, check=True).stdout)
        for fn in cov["data"][0]["functions"]:
            if module not in fn["name"]: continue
            for r in fn["regions"]:
                sl, sc, el, ec, count = r[0], r[1], r[2], r[3], r[4]
                key = (fn["filenames"][0], fn["name"], sl, sc, el, ec)
                counts[key][s] = count
                for tf, ts, te in truth_hunks:
                    if fn["filenames"][0].endswith(tf) and not (el < ts or sl > te):
                        truth_keys.add(key)
    return counts, all_pos, all_neg, truth_keys

def fn_score(c_dict, pos_set, neg_set, metric):
    pos_vals = [c_dict.get(s, 0) for s in pos_set]
    neg_vals = [c_dict.get(s, 0) for s in neg_set]
    if metric == "ochiai":
        ef = sum(1 for x in neg_vals if x > 0)
        ep = sum(1 for x in pos_vals if x > 0)
        nf = len(neg_vals) - ef
        denom = math.sqrt((ef + nf) * (ef + ep)) if (ef+nf)*(ef+ep) > 0 else 0
        return ef / denom if denom > 0 else 0.0
    elif metric == "delta":
        mP = statistics.mean(pos_vals) if pos_vals else 0.0
        mN = statistics.mean(neg_vals) if neg_vals else 0.0
        return mN - mP
    return 0.0

def truth_rank(counts, truth_keys, pos_set, neg_set, metric):
    by_fn = defaultdict(float)
    for key, c_dict in counts.items():
        s = fn_score(c_dict, pos_set, neg_set, metric)
        if s > by_fn[(key[0], key[1])]:
            by_fn[(key[0], key[1])] = s
    truth_fns = set((k[0], k[1]) for k in truth_keys)
    ordered = sorted(by_fn.items(), key=lambda kv: -kv[1])
    for r, ((fname, fn_name), score) in enumerate(ordered, start=1):
        if (fname, fn_name) in truth_fns: return r
    return None

def greedy_reduce(counts, truth_keys, start_pos, start_neg, metric, max_iter=30):
    pos = list(start_pos); neg = list(start_neg)
    best_r = truth_rank(counts, truth_keys, pos, neg, metric)
    if best_r is None: return None, pos, neg
    iters = 0
    while iters < max_iter:
        iters += 1
        cand_drop = None; cand_r = best_r; cand_kind = None
        for s in pos:
            if len(pos) <= 2: break
            test = [x for x in pos if x != s]
            r = truth_rank(counts, truth_keys, test, neg, metric)
            if r is not None and r < cand_r:
                cand_r = r; cand_drop = s; cand_kind = "pos"
        for s in neg:
            if len(neg) <= 2: break
            test = [x for x in neg if x != s]
            r = truth_rank(counts, truth_keys, pos, test, metric)
            if r is not None and r < cand_r:
                cand_r = r; cand_drop = s; cand_kind = "neg"
        if cand_drop is None: break
        if cand_kind == "pos": pos = [x for x in pos if x != cand_drop]
        else: neg = [x for x in neg if x != cand_drop]
        best_r = cand_r
        if best_r == 1: break
    return best_r, pos, neg

# ---------- variant selection ----------
def stratified_sample():
    """Pick a stratified sample across ochiai_fn rank tiers from matrix_ranks.jsonl."""
    matrix = ROOT / "faultloc-results" / "matrix_ranks.jsonl"
    by_tier = {"11-30":[], "31-100":[], "100+":[]}
    seen = set()
    for line in matrix.read_text().splitlines():
        r = json.loads(line)
        if r.get("config_n") != "N100" or r.get("config_init") != "with": continue
        if r.get("status") != "ok": continue
        key = (r["workload"], r["variant"])
        if key in seen: continue
        if r.get("ochiai_fn") is None or r["ochiai_fn"] <= 10: continue
        if r.get("kind") != "patch": continue  # batch supports patch only
        if r.get("pos", 0) < 5 or r.get("neg", 0) < 5: continue
        seen.add(key)
        rank = r["ochiai_fn"]
        tier = "11-30" if rank <= 30 else ("31-100" if rank <= 100 else "100+")
        by_tier[tier].append(r)
    rng = random.Random(42)
    sample = []
    for tier in ["11-30","31-100","100+"]:
        rng.shuffle(by_tier[tier])
        take = min(5, len(by_tier[tier]))
        for r in by_tier[tier][:take]:
            r["_tier"] = tier
            sample.append(r)
    return sample

def main():
    sample = stratified_sample()
    log(f"# Sample: {len(sample)} variants across tiers {set(r['_tier'] for r in sample)}")
    for r in sample:
        log(f"  {r['_tier']:>6}  {r['workload']:<22} {r['variant']:<40} ochiai={r['ochiai_fn']:>4}  delta={r.get('delta_fn','?'):>5}")

    # Truncate / append to results file
    if RESULTS_FILE.exists():
        RESULTS_FILE.rename(RESULTS_FILE.with_suffix(".jsonl.bak"))

    for i, r in enumerate(sample, start=1):
        log(f"\n=== [{i}/{len(sample)}] {r['workload']}/{r['variant']} (tier {r['_tier']}, baseline ochiai_fn={r['ochiai_fn']}) ===")
        truth, task = truth_for_variant(r["workload"], r["variant"])
        if not truth or not task:
            log("  SKIP: cannot derive truth")
            continue
        if not prepare_variant(r["workload"], task):
            log("  SKIP: patch did not apply")
            continue
        try:
            t0 = time.time()
            ok = rebuild_and_run(r["workload"], task)
            if not ok:
                log("  SKIP: rebuild/run failed")
                continue
            log(f"  rebuild+run: {time.time()-t0:.0f}s")
            t0 = time.time()
            wdir = ROOT / "workloads" / "Rust" / r["workload"]
            module = module_for(r["workload"])
            counts, all_pos, all_neg, truth_keys = load_count_matrix(wdir, module, truth)
            log(f"  loaded matrix in {time.time()-t0:.0f}s: {len(counts)} regions, {len(all_pos)} pos, {len(all_neg)} neg, {len(truth_keys)} truth keys")
            if not truth_keys:
                log("  SKIP: no region matched truth")
                continue
            # Baseline + greedy for both metrics
            t0 = time.time()
            results = {}
            for m in ["ochiai", "delta"]:
                base = truth_rank(counts, truth_keys, all_pos, all_neg, m)
                best, _, _ = greedy_reduce(counts, truth_keys, all_pos, all_neg, m)
                results[m] = {"baseline": base, "best_subset": best}
            log(f"  existential search: {time.time()-t0:.0f}s")
            log(f"  ochiai: {results['ochiai']['baseline']} -> {results['ochiai']['best_subset']}")
            log(f"  delta:  {results['delta']['baseline']} -> {results['delta']['best_subset']}")
            with open(RESULTS_FILE, "a") as f:
                f.write(json.dumps({
                    "workload": r["workload"], "variant": r["variant"],
                    "tier": r["_tier"], "matrix_baseline": r["ochiai_fn"],
                    "n_pos": len(all_pos), "n_neg": len(all_neg),
                    "n_regions": len(counts), "n_truth_keys": len(truth_keys),
                    **{f"{m}_{k}": v for m, d in results.items() for k, v in d.items()},
                }) + "\n")
        finally:
            cleanup_variant(r["workload"], task)

    log(f"\nDone. Results in {RESULTS_FILE}")

if __name__ == "__main__":
    main()
