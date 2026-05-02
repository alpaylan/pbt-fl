#!/usr/bin/env python3
"""
Run the full faultloc suite using `crabcheck::quickcheck_with_locate!` via
`cargo test`. For each variant in matrix_jobs.tsv:

  1. Apply the mutation (patch or marauders set).
  2. cargo test --release --features <extra> --test locate -- --nocapture --exact <test_name>
  3. Parse the `@@LOCATE@@ <json>` line from stdout.
  4. Revert the mutation.

Saves per-variant results to faultloc-results/locate_full_suite.jsonl.
Resumable: re-running skips variants whose status is already "ok" or
"no_truth" unless `--rerun` is passed.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/Users/akeles/Programming/projects/PbtBenchmark/faultloc")
WORKLOADS = ROOT / "workloads" / "Rust"
JOBS_TSV = ROOT / "scripts" / "matrix_jobs.tsv"
RESULTS = ROOT / "faultloc-results" / "locate_full_suite.jsonl"
LOG_DIR = ROOT / "scripts" / "log_locate"
LOG_DIR.mkdir(exist_ok=True)
RESULTS.parent.mkdir(exist_ok=True, parents=True)

sys.path.insert(0, str(ROOT / "scripts"))
from compute_faultloc_ranks import parse_etna_tasks, resolve_truth

RUSTFLAGS = (
    "-C instrument-coverage -C link-dead-code -C codegen-units=1 -C debuginfo=2"
)


def pascal_to_snake(s: str) -> str:
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    s = re.sub(r"([A-Z])([A-Z][a-z])", r"\1_\2", s)
    return s.lower()


def load_jobs():
    with open(JOBS_TSV) as f:
        rows = [line.rstrip("\n").split("\t") for line in f.readlines()[1:]]
    return [
        dict(zip(["workload", "property", "short", "kind_arg", "extra"], r + [""] * (5 - len(r))))
        for r in rows if len(r) >= 4
    ]


def workload_cargo_dir(workload: str) -> Path:
    """Return the directory where `cargo test` should run.

    Most workloads: `workloads/Rust/<workload>/`. The `time` workload is a
    Cargo workspace whose default member is the `time/` sub-crate; running
    cargo test from the workspace root works thanks to default-members.
    """
    return WORKLOADS / workload


def apply_mutation(w_dir: Path, kind_arg: str):
    kind, _, arg = kind_arg.partition(":")
    if kind == "patch":
        for flags in ([], ["-C0"]):
            rc = subprocess.run(
                ["git", "apply", "--ignore-whitespace", *flags, arg],
                cwd=w_dir, capture_output=True,
            ).returncode
            if rc == 0:
                return True, ("patch", arg, None)
        return False, ("patch", arg, None)
    elif kind == "marauders":
        files_out = subprocess.run(
            ["marauders", "list"], cwd=w_dir, capture_output=True, text=True
        ).stdout
        marauder_files = []
        for line in files_out.splitlines():
            if f'"{arg}"' in line and ".rs" in line:
                marauder_files.append(line.split(":")[0].lstrip("./"))
        backup = f"/tmp/marauder_backup_{w_dir.name}_{os.getpid()}.tar"
        if marauder_files:
            subprocess.run(
                ["tar", "-cf", backup, *marauder_files],
                cwd=w_dir, check=True,
            )
        rc = subprocess.run(
            ["marauders", "set", "--variant", arg],
            cwd=w_dir, capture_output=True,
        ).returncode
        return rc == 0, ("marauders", arg, (backup, marauder_files))
    return False, (kind, arg, None)


def revert_mutation(w_dir: Path, state):
    kind, arg, info = state
    if kind == "patch":
        for flags in ([], ["-C0"]):
            rc = subprocess.run(
                ["git", "apply", "-R", "--ignore-whitespace", *flags, arg],
                cwd=w_dir, capture_output=True,
            ).returncode
            if rc == 0:
                return
        files = []
        try:
            with open(arg) as f:
                for line in f:
                    if line.startswith("+++ b/"):
                        files.append(line[6:].strip())
        except FileNotFoundError:
            pass
        if files:
            subprocess.run(["git", "checkout", "--"] + files, cwd=w_dir, capture_output=True)
    elif kind == "marauders":
        backup, files = info
        if backup and Path(backup).exists() and files:
            subprocess.run(["tar", "-xf", backup], cwd=w_dir, check=True)
            os.unlink(backup)


def run_test(cargo_dir: Path, test_name: str, extra_features: str, log_path: Path) -> dict | None:
    cmd = ["cargo", "test", "--release"]
    if extra_features:
        cmd += ["--features", extra_features]
    cmd += ["--test", "locate", "--", "--nocapture", "--exact", test_name]

    env = os.environ.copy()
    env["CARGO_INCREMENTAL"] = "0"
    env["RUSTFLAGS"] = RUSTFLAGS
    # Match the v2 matrix budget so the rank-with-prior calibration holds.
    # Lower budgets cause most regions to tie at ochiai=delta=0 and the
    # rank-1 rules trivially fire HIGH on whichever region sorts first.
    env.setdefault("CRABCHECK_PROFILING_MUTATIONS", "1000")
    env.setdefault("CRABCHECK_PROFILING_INITIAL_PASSES", "100")
    env.setdefault("CRABCHECK_PROFILING_RANDOM_ITERS", "20000")

    with open(log_path, "wb") as lf:
        try:
            # Cargo test triggers a full instrument-coverage rebuild per variant
            # (mutation invalidates the cache). With v2-budget iter counts the
            # combined build+run+analyze can run 15-25 minutes on larger crates.
            subprocess.run(cmd, cwd=cargo_dir, env=env, stdout=lf, stderr=lf, timeout=2400)
        except subprocess.TimeoutExpired:
            lf.write(b"\n[driver: TIMEOUT after 2400s]\n")
            return None

    output = log_path.read_text(errors="replace")
    locate_lines = [line for line in output.splitlines() if line.startswith("@@LOCATE@@ ")]
    if not locate_lines:
        return None
    try:
        return json.loads(locate_lines[-1][len("@@LOCATE@@ "):])
    except json.JSONDecodeError:
        return None


def derive_truth_in_top(suspect_list, truths):
    """Return (in_top_5, rank_post_prior or None)."""
    for s in suspect_list:
        for tf, ts, te in truths:
            if s["file"].endswith(tf) and not (s["end_line"] < ts or s["start_line"] > te):
                return True, s["rank"]
    return False, None


def main():
    jobs = load_jobs()
    if "--filter" in sys.argv:
        idx = sys.argv.index("--filter")
        pat = sys.argv[idx + 1]
        jobs = [j for j in jobs if pat in f"{j['workload']}/{j['short']}"]

    out_records = []
    if RESULTS.exists():
        out_records = [
            json.loads(l) for l in RESULTS.read_text().splitlines() if l.strip()
        ]
    done_keys = (
        set()
        if "--rerun" in sys.argv
        else {(r["workload"], r["variant"]) for r in out_records if r.get("status") in ("ok", "no_truth")}
    )

    print(f"# {len(jobs)} variants total, {len(done_keys)} already done")

    for i, j in enumerate(jobs, start=1):
        key = (j["workload"], j["short"])
        if key in done_keys:
            continue
        cargo_dir = workload_cargo_dir(j["workload"])
        toml = cargo_dir / "etna.toml"
        if not toml.exists():
            continue
        task = next((t for t in parse_etna_tasks(toml) if t["short"] == j["short"]), None)
        if task is None:
            continue
        truths = resolve_truth(cargo_dir, task)
        rec = {
            "workload": j["workload"],
            "variant": j["short"],
            "property": j["property"],
            "kind_arg": j["kind_arg"],
            "truth_preview": (
                f"{truths[0][0]}:{truths[0][1]}-{truths[0][2]}" if truths else "NO_TRUTH"
            ),
        }
        if not truths:
            rec["status"] = "no_truth"
            out_records.append(rec)
            RESULTS.write_text("\n".join(json.dumps(r) for r in out_records) + "\n")
            print(f"[{i}/{len(jobs)}] {j['workload']}/{j['short']} -> no_truth")
            continue

        test_name = f"locate_{pascal_to_snake(j['property'])}"
        log_path = LOG_DIR / f"{j['workload'].replace('/', '_')}__{j['short']}.log"
        log_path.unlink(missing_ok=True)
        t0 = time.time()
        print(
            f"[{i}/{len(jobs)}] {j['workload']}/{j['short']} ({test_name}) ",
            end="", flush=True,
        )

        state = ("?", "?", None)
        try:
            ok, state = apply_mutation(cargo_dir, j["kind_arg"])
            if not ok:
                rec["status"] = "apply_failed"
                rec["elapsed_s"] = round(time.time() - t0, 1)
                print(f"-> apply_failed ({rec['elapsed_s']}s)")
                out_records.append(rec)
                RESULTS.write_text("\n".join(json.dumps(r) for r in out_records) + "\n")
                continue

            locate = run_test(cargo_dir, test_name, j.get("extra", ""), log_path)
            if locate is None:
                rec["status"] = "no_locate_output"
                print(f"-> no_locate_output (see {log_path.name})", end="")
            else:
                rec["status"] = "ok"
                rec["locate_status"] = locate.get("status")
                rec["n_panics"] = locate.get("n_panics", 0)
                rec["n_suspects"] = locate.get("n_suspects", 0)
                rec["diagnostics"] = locate.get("diagnostics", [])
                top = locate.get("top") or {}
                rec["top_function"] = top.get("function")
                rec["top_file"] = top.get("file")
                rec["top_lines"] = [top.get("start_line"), top.get("end_line")]
                rec["top_confidence"] = top.get("confidence")
                rec["top_confidence_rule"] = top.get("confidence_rule")
                rec["top_panic_overlap"] = top.get("panic_overlap")
                rec["top_ochiai"] = top.get("ochiai")
                rec["top_delta"] = top.get("delta")
                in_top_5, rank = derive_truth_in_top(locate.get("top_5", []), truths)
                rec["truth_in_top_5"] = in_top_5
                rec["truth_rank_post_prior"] = rank
                rec["truth_in_top_1"] = rank == 1
                print(
                    f"-> {rec['locate_status']} top1={rec['truth_in_top_1']} top5={rec['truth_in_top_5']} "
                    f"band={rec['top_confidence']} rule={rec['top_confidence_rule']}",
                    end="",
                )
        except Exception as e:
            rec["status"] = f"error: {e}"
            print(f"-> error: {e}", end="")
        finally:
            try:
                if state[0] != "?":
                    revert_mutation(cargo_dir, state)
            except Exception as e:
                print(f"  [revert error: {e}]", end="")

        rec["elapsed_s"] = round(time.time() - t0, 1)
        print(f"  ({rec['elapsed_s']}s)")
        out_records.append(rec)
        RESULTS.write_text("\n".join(json.dumps(r) for r in out_records) + "\n")

    print(f"\nWrote {len(out_records)} records to {RESULTS}")


if __name__ == "__main__":
    main()
