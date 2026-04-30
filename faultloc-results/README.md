# faultloc-results

Persisted outputs of `crabcheck-profiling-fast-analyze` + stability experiments on each patched workload variant. See `REPORT.md` for the consolidated writeup.

## Quick start

```bash
cd workloads/Rust/<crate>
git apply patches/<variant>.patch                          # kind=patch
# or: marauders set --variant <variant_id>                 # kind=marauders

mkdir -p coverage
CARGO_INCREMENTAL=0 RUSTFLAGS="-C instrument-coverage -C link-dead-code \
  -C codegen-units=1 -C inline-threshold=0 -C llvm-args=-inline-threshold=0 \
  -C debuginfo=2" cargo build --release --bin etna-faultloc [--features etna]
LLVM_PROFILE_FILE="coverage/snapshot_%p-%m.profraw" \
  ./target/release/etna-faultloc crabcheck <PropertyName> 200

crabcheck-profiling-fast-analyze coverage <module> ./target/release/etna-faultloc \
  --print-json > out.json
```

`fast-analyze` handles llvm-profdata merge, llvm-cov export, aggregation, and demangling in a single Rust process. No intermediate `jsondata/` on disk.

## Env-var knobs (all optional)

| Var | Default | Purpose |
|---|---:|---|
| `CRABCHECK_PROFILING_MUTATIONS` | 1000 | Mutation-loop bound |
| `CRABCHECK_PROFILING_INITIAL_PASSES` | 100 | Snapshots from the initial random sweep |
| `CRABCHECK_PROFILING_RANDOM_ITERS` | 20000 | Outer sweep bound before giving up |
| `CRABCHECK_PROFILING_MAX_SHRINK_STEPS` | 1000 | Shrink safety cap |

## Layout

```
<crate>/<variant>/
├── *.json                  raw fast-analyze --print-json output
├── rankings.md             metadata + per-metric ground-truth rank table
├── matrix/                 (optional) mut × init subset grid
└── multi-trial-*/          (optional) K-trial stability experiments
```

## Output JSON schema

```jsonc
{
  "positive_samples": N,
  "negative_samples": M,
  "regions": [
    {
      "file": "…/source.rs",
      "function": "demangled::function::name",
      "start_line": 508, "start_col": 13, "end_line": 508, "end_col": 45,
      "positive_avg": 0.0,
      "negative_avg": 1.0,
      "delta": 1.0,
      "ef": 420, "ep": 0,
      "nf": 0,   "np": 81,
      "suspiciousness": {
        "tarantula": 1.0, "ochiai": 1.0, "dstar": 1.8e308,
        "jaccard": 1.0, "op2": 420.0
      }
    }
  ]
}
```

`delta > 0` ⇔ region fires more on failing snapshots than passing. Default human view filters to these; JSON view includes every region.

## indices.json schema (written by crabcheck profiling)

```jsonc
{
  "positives": [1001, 1002, …, 137, …],   // snapshot indices (mutation-loop < base, init-sweep ≥ base)
  "negatives": [0, 13, 42, …],
  "positive_examples": […],                // parallel to .positives
  "negative_examples": […],                // parallel to .negatives
  "config": {
    "max_mutations": 1000,
    "max_initial_passes": 100,
    "initial_pass_base": 1001,
    "random_iters": 20000,
    "shrink_steps": 29                     // how many shrink iterations ran
  }
}
```

The `config.initial_pass_base` is the smallest index reserved for initial-sweep positives. Downstream scripts that need to partition mutation-loop vs initial-sweep positives should read this field, never hardcode the value.
