#!/usr/bin/env python3
"""
Sampled crash-stack-prior experiment. For each picked variant:
  1. Apply patch / marauders set the buggy variant
  2. Rebuild the instrumented binary
  3. Run faultloc once (N=200, K=50)
  4. Capture coverage/panic_locations.jsonl + run fast-analyze
  5. Compute baseline ranks (ochiai, avg_norm_od) and prior-boosted ranks
  6. Revert to clean state, write one record per variant to crash_prior_sample.jsonl

Picks ~25 variants: all likely-panic-bug variants (by name heuristic) plus
random non-panic ones. Caller may pass --all to run the entire matrix_jobs.tsv.
"""
import json, os, random, re, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path("/Users/akeles/Programming/projects/PbtBenchmark/faultloc")
WORKLOADS = ROOT / "workloads" / "Rust"
JOBS_TSV = ROOT / "scripts" / "matrix_jobs.tsv"
RESULTS_DIR = ROOT / "faultloc-results"
SAMPLE_OUT = RESULTS_DIR / "crash_prior_sample.jsonl"
RUN_LOG = RESULTS_DIR / "crash_prior_runs"
RUN_LOG.mkdir(parents=True, exist_ok=True)

RUSTFLAGS = (
    "-C instrument-coverage -C link-dead-code -C codegen-units=1 "
    "-C inline-threshold=0 -C llvm-args=-inline-threshold=0 -C debuginfo=2"
)
PANIC_HINT = re.compile(r"panic|assert|overflow|underflow|out_of_bounds|oob|capacity|nan|div_zero|div_by", re.I)

sys.path.insert(0, str(ROOT / "scripts"))
from compute_faultloc_ranks import (
    parse_etna_tasks, resolve_truth, aggregate_functions,
    region_matches, sbfl_key,
)
from aggregate_ranks import normalize_metric, rank_per_metric, truth_rank_via_score

def load_jobs():
    with open(JOBS_TSV) as f:
        rows = [line.rstrip("\n").split("\t") for line in f.readlines()[1:]]
    return [dict(zip(["workload", "property", "short", "kind_arg", "extra"], r + [""] * (5 - len(r))))
            for r in rows if len(r) >= 4]

def panic_likely(short):
    return bool(PANIC_HINT.search(short))

def pick_sample(rows, n_other=5, seed=0):
    panicy = [r for r in rows if panic_likely(r["short"])]
    others = [r for r in rows if not panic_likely(r["short"])]
    rng = random.Random(seed)
    extra = rng.sample(others, min(n_other, len(others)))
    return panicy + extra

def find_truth(workload, short):
    """Returns list of (file, lo, hi) hunks for this variant, or None."""
    w_dir = WORKLOADS / workload
    toml = w_dir / "etna.toml"
    if not toml.exists(): return None, None
    for task in parse_etna_tasks(toml):
        if task["short"] == short:
            return resolve_truth(w_dir, task), task
    return None, None

def run_cmd(cmd, cwd, log, env=None, timeout=600):
    with open(log, "ab") as lf:
        lf.write(f"# {' '.join(cmd)}\n".encode())
        lf.flush()
        return subprocess.run(cmd, cwd=cwd, env=env, stdout=lf, stderr=subprocess.STDOUT, timeout=timeout)

def apply_variant(w_dir, kind, arg, log):
    if kind == "patch":
        # Try with then without context.
        rc = subprocess.run(["git", "apply", "--ignore-whitespace", arg], cwd=w_dir, capture_output=True).returncode
        if rc != 0:
            rc = subprocess.run(["git", "apply", "--ignore-whitespace", "-C0", arg], cwd=w_dir, capture_output=True).returncode
        return rc == 0
    elif kind == "marauders":
        files = subprocess.run(["marauders", "list"], cwd=w_dir, capture_output=True, text=True).stdout
        marauder_files = []
        for line in files.splitlines():
            if f'"{arg}"' in line and ".rs" in line:
                marauder_files.append(line.split(":")[0].lstrip("./"))
        # Backup
        backup = f"/tmp/marauder_backup_{w_dir.name}_{os.getpid()}.tar"
        if marauder_files:
            subprocess.run(["tar", "-cf", backup] + marauder_files, cwd=w_dir, check=True)
        rc = subprocess.run(["marauders", "set", "--variant", arg], cwd=w_dir, capture_output=True).returncode
        return rc == 0, backup, marauder_files
    return False

def revert_variant(w_dir, kind, arg, marauder_state):
    if kind == "patch":
        for flag in ["", "-C0"]:
            args = ["git", "apply", "-R", "--ignore-whitespace"] + ([flag] if flag else []) + [arg]
            if subprocess.run(args, cwd=w_dir, capture_output=True).returncode == 0:
                return
        # Hard fallback: checkout patched files
        files = []
        with open(arg) as f:
            for line in f:
                if line.startswith("+++ b/"):
                    files.append(line[6:].strip())
        if files:
            subprocess.run(["git", "checkout", "--"] + files, cwd=w_dir, capture_output=True)
    elif kind == "marauders":
        ok, backup, files = marauder_state
        if Path(backup).exists() and files:
            subprocess.run(["tar", "-xf", backup], cwd=w_dir, check=True)
            os.unlink(backup)

def get_module(w_dir):
    steps = w_dir / "steps.sh"
    if not steps.exists(): return w_dir.name.replace("-", "_")
    m = re.search(r"fast-analyze coverage ([a-zA-Z0-9_]+)", steps.read_text())
    return m.group(1) if m else w_dir.name.replace("-", "_")

def parse_panic_locs(panic_jsonl):
    locs = set()
    n = 0
    if not panic_jsonl.exists(): return locs, 0
    for line in panic_jsonl.read_text().splitlines():
        if not line.strip(): continue
        n += 1
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if "file" in entry and "line" in entry:
            locs.add((entry["file"], int(entry["line"])))
        for bt_line in entry.get("bt", "").split("\n"):
            mm = re.search(r"at ([^\s:]+):(\d+):\d+", bt_line)
            if mm:
                fn, ln = mm.group(1), int(mm.group(2))
                if fn.startswith("./src/") or fn.startswith("src/"):
                    fn_norm = fn[2:] if fn.startswith("./") else fn
                    if fn_norm.startswith("src/bin/") or fn_norm == "src/etna.rs":
                        continue
                    locs.add((fn_norm, ln))
    return locs, n

def region_panic_score(region, locs):
    rf, sl, el = region.get("file", ""), region.get("start_line", -1), region.get("end_line", -1)
    for pf, pl in locs:
        if rf.endswith(pf) and sl <= pl <= el:
            return 1
    return 0

def compute_ranks(regions, truths, panic_locs):
    grouped = aggregate_functions(regions)
    if not grouped:
        return {"n_groups": 0}
    N = len(grouped)
    panic_overlap = [region_panic_score(g, panic_locs) for g in grouped]
    no = normalize_metric(grouped, "ochiai")
    nd = normalize_metric(grouped, "delta")
    avg = [(no[i] + nd[i]) / 2.0 for i in range(N)]
    ochiai_score = [-rank_per_metric(grouped, "ochiai")[i] for i in range(N)]
    out = {
        "n_groups": N,
        "n_panic_overlap_groups": sum(panic_overlap),
        "ochiai_rank": truth_rank_via_score(grouped, ochiai_score, truths),
        "avg_norm_od_rank": truth_rank_via_score(grouped, avg, truths),
        "prior_only_rank": truth_rank_via_score(grouped, panic_overlap, truths),
        "prior_avg_rank": truth_rank_via_score(grouped, [panic_overlap[i] * 10 + avg[i] for i in range(N)], truths),
        "prior_ochiai_rank": truth_rank_via_score(grouped, [panic_overlap[i] * 1e6 + ochiai_score[i] for i in range(N)], truths),
    }
    return out

def process_variant(row):
    workload = row["workload"]; short = row["short"]; prop = row["property"]
    kind = row["kind_arg"].split(":", 1)[0]
    arg = row["kind_arg"].split(":", 1)[1]
    extra = row["extra"]
    w_dir = WORKLOADS / workload
    log = RUN_LOG / f"{workload}__{short}.log"
    log.unlink(missing_ok=True)

    truths, _task = find_truth(workload, short)
    if not truths:
        return {"workload": workload, "variant": short, "status": "no_truth"}

    module = get_module(w_dir)
    rec = {"workload": workload, "variant": short, "kind": kind,
           "property": prop, "module": module, "panic_likely": panic_likely(short),
           "truth_preview": f"{truths[0][0]}:{truths[0][1]}-{truths[0][2]}"}
    t0 = time.time()
    marauder_state = (False, None, [])
    try:
        if kind == "patch":
            if not apply_variant(w_dir, kind, arg, log):
                rec["status"] = "patch_apply_failed"; return rec
        else:
            ok, backup, files = apply_variant(w_dir, kind, arg, log)
            marauder_state = (ok, backup, files)
            if not ok: rec["status"] = "marauders_failed"; return rec

        feat_args = ["--features", extra] if extra else []
        env = os.environ.copy()
        env["CARGO_INCREMENTAL"] = "0"
        env["RUSTFLAGS"] = RUSTFLAGS
        rc = run_cmd(["cargo", "build", "--release", "--bin", "etna-faultloc"] + feat_args,
                     cwd=w_dir, log=log, env=env, timeout=600)
        if rc.returncode != 0:
            rec["status"] = "build_failed"; return rec

        # Wipe coverage
        for sub in ["coverage", "profdata", "jsondata"]:
            shutil.rmtree(w_dir / sub, ignore_errors=True)
        (w_dir / "coverage").mkdir()

        env2 = os.environ.copy()
        env2["CRABCHECK_PROFILING_MUTATIONS"] = "200"
        env2["CRABCHECK_PROFILING_INITIAL_PASSES"] = "50"
        env2["LLVM_PROFILE_FILE"] = "coverage/snapshot_%p-%m.profraw"
        rc = run_cmd(["./target/release/etna-faultloc", "crabcheck", prop],
                     cwd=w_dir, log=log, env=env2, timeout=600)
        # Allow non-zero exit (the binary may panic out of the loop in extreme cases)
        if not (w_dir / "coverage" / "indices.json").exists():
            rec["status"] = "no_indices"; return rec

        analysis_json = subprocess.run(
            ["crabcheck-profiling-fast-analyze", "coverage", module,
             str(w_dir / "target/release/etna-faultloc"), "--print-json"],
            cwd=w_dir, capture_output=True, text=True, timeout=600)
        if analysis_json.returncode != 0 or not analysis_json.stdout.strip():
            rec["status"] = "analysis_failed"; return rec
        data = json.loads(analysis_json.stdout)
        regions = data.get("regions", [])
        rec["positives"] = data.get("positive_samples", 0)
        rec["negatives"] = data.get("negative_samples", 0)

        panic_locs, n_panics = parse_panic_locs(w_dir / "coverage" / "panic_locations.jsonl")
        rec["n_panic_events"] = n_panics
        rec["n_panic_locs"] = len(panic_locs)
        rec.update(compute_ranks(regions, truths, panic_locs))
        rec["status"] = "ok"
    finally:
        revert_variant(w_dir, kind, arg, marauder_state)
        rec["elapsed"] = round(time.time() - t0, 1)
    return rec

def main():
    rows = load_jobs()
    if "--all" in sys.argv:
        sample = rows
    else:
        sample = pick_sample(rows, n_other=5)
    print(f"# Sample: {len(sample)} variants ({sum(panic_likely(r['short']) for r in sample)} likely-panic, "
          f"{sum(not panic_likely(r['short']) for r in sample)} other)")

    out_lines = []
    for i, row in enumerate(sample, start=1):
        print(f"[{i}/{len(sample)}] {row['workload']}/{row['short']} ", end="", flush=True)
        rec = process_variant(row)
        print(f"-> status={rec.get('status', '?')} "
              f"ochiai={rec.get('ochiai_rank')} prior={rec.get('prior_ochiai_rank')} "
              f"panics={rec.get('n_panic_events')} ({rec.get('elapsed', 0)}s)")
        out_lines.append(json.dumps(rec))
        SAMPLE_OUT.write_text("\n".join(out_lines) + "\n")  # incremental save

    print(f"\nWrote {len(out_lines)} records to {SAMPLE_OUT}")

if __name__ == "__main__":
    main()
