#!/bin/bash
# Run a 6-config faultloc matrix for one workload+variant.
#
# Steps:
#   1. Apply patch / marauders set
#   2. Rebuild instrumented binary
#   3. Run once with CRABCHECK_PROFILING_MUTATIONS=1000 + INITIAL_PASSES=100
#   4. Subset coverage/indices.json into 6 configs and run fast-analyze on each
#   5. Save results as faultloc-results/<workload>/<short>/matrix-N1000/<config>.json
#   6. Revert patch / restore marauders backup
#
# Usage: validate_faultloc_matrix.sh <workload> <property> <short> <kind:arg> [extra_features]

set -euo pipefail

WORKLOAD="${1:?workload}"
PROPERTY="${2:?property}"
SHORT_NAME="${3:?short_name}"
KIND_ARG="${4:?kind:arg (patch:<path> | marauders:<variant>)}"
EXTRA_FEATURES="${5:-}"

KIND="${KIND_ARG%%:*}"
ARG="${KIND_ARG#*:}"

ROOT=/Users/akeles/Programming/projects/PbtBenchmark/faultloc
WDIR="$ROOT/workloads/Rust/$WORKLOAD"
OUT_DIR="$ROOT/faultloc-results/$WORKLOAD/$SHORT_NAME/matrix-N1000"
MARAUDER_BACKUP="/tmp/marauder_backup_${WORKLOAD}_$$.tar"

mkdir -p "$OUT_DIR"

cleanup() {
  case "$KIND" in
    patch)
      # Try both with-context and -C0 reverts; if either fails, fall back to
      # a hard checkout of the patch's modified files so we never leave the
      # next variant with a dirty source tree.
      (cd "$WDIR" && \
        (git apply -R --ignore-whitespace "$ARG" 2>/dev/null \
         || git apply -R --ignore-whitespace -C0 "$ARG" 2>/dev/null \
         || git checkout -- $(grep -E '^\+\+\+ b/' "$ARG" | sed 's|^+++ b/||') 2>/dev/null)) || true
      ;;
    marauders)
      [ -f "$MARAUDER_BACKUP" ] && (cd "$WDIR" && tar -xf "$MARAUDER_BACKUP") && rm -f "$MARAUDER_BACKUP" || true
      ;;
  esac
}
trap cleanup EXIT

case "$KIND" in
  patch)
    echo "[$WORKLOAD/$SHORT_NAME] applying patch"
    (cd "$WDIR" && \
      (git apply --ignore-whitespace "$ARG" 2>/dev/null \
       || git apply --ignore-whitespace -C0 "$ARG"))
    ;;
  marauders)
    FILES=$(cd "$WDIR" && marauders list 2>/dev/null | grep -E "variants: \[\"$ARG\"\]" | sed 's|:.*||' | head -1)
    [ -z "$FILES" ] && { echo "ERROR: marauders list found no $ARG"; exit 1; }
    (cd "$WDIR" && tar -cf "$MARAUDER_BACKUP" $FILES)
    (cd "$WDIR" && marauders set --variant "$ARG")
    ;;
  *) echo "Unknown kind: $KIND"; exit 2 ;;
esac

echo "[$WORKLOAD/$SHORT_NAME] rebuilding"
FEATURE_ARGS=""
[ -n "$EXTRA_FEATURES" ] && FEATURE_ARGS="--features $EXTRA_FEATURES"
(cd "$WDIR" && \
  CARGO_INCREMENTAL=0 \
  RUSTFLAGS="-C instrument-coverage -C link-dead-code -C codegen-units=1 -C inline-threshold=0 -C llvm-args=-inline-threshold=0 -C debuginfo=2" \
  cargo build --release --bin etna-faultloc $FEATURE_ARGS 2>&1 | tail -3)

echo "[$WORKLOAD/$SHORT_NAME] wiping coverage"
rm -rf "$WDIR/coverage" "$WDIR/profdata" "$WDIR/jsondata"
mkdir -p "$WDIR/coverage"

MODULE=$(grep -oE 'fast-analyze coverage [a-z_]+' "$WDIR/steps.sh" | head -1 | awk '{print $3}')

echo "[$WORKLOAD/$SHORT_NAME] running N=1000 K=100 (module=$MODULE)"
(cd "$WDIR" && \
  CRABCHECK_PROFILING_MUTATIONS=1000 \
  CRABCHECK_PROFILING_INITIAL_PASSES=100 \
  LLVM_PROFILE_FILE="coverage/snapshot_%p-%m.profraw" \
  ./target/release/etna-faultloc crabcheck "$PROPERTY" 2>&1 | tail -1)

if [ ! -s "$WDIR/coverage/indices.json" ]; then
  echo "[$WORKLOAD/$SHORT_NAME] no indices.json — bug not triggered"
  exit 0
fi

# Preserve the captured panic locations alongside the matrix outputs. Each
# panic event is one JSONL line (immediate (file, line) + full backtrace).
# Variants whose buggy path doesn't panic will not produce this file; the
# crash-stack prior is then a no-op for them.
if [ -s "$WDIR/coverage/panic_locations.jsonl" ]; then
  cp "$WDIR/coverage/panic_locations.jsonl" "$OUT_DIR/panic_locations.jsonl"
fi

# Backup the original full-run indices.json so we can subset+restore it.
cp "$WDIR/coverage/indices.json" "$WDIR/coverage/indices.full.json"

for mut in 100 500 1000; do
  for init_flag in 1 0; do
    init_label=$([ $init_flag -eq 1 ] && echo with || echo without)
    out_file="$OUT_DIR/N${mut}-${init_label}.json"
    # Write subsetted indices.json in place of the original.
    python3 "$ROOT/scripts/subset_indices.py" "$WDIR/coverage" "$mut" "$init_flag" "$WDIR/coverage/indices.json"
    (cd "$WDIR" && crabcheck-profiling-fast-analyze coverage "$MODULE" ./target/release/etna-faultloc --print-json > "$out_file" 2>/dev/null)
    # Quick stats from the analysis
    pos=$(jq '.positive_samples' "$out_file" 2>/dev/null || echo "?")
    neg=$(jq '.negative_samples' "$out_file" 2>/dev/null || echo "?")
    nreg=$(jq '.regions | length' "$out_file" 2>/dev/null || echo "?")
    echo "  N=$mut init=$init_label -> pos=$pos neg=$neg regions=$nreg"
  done
done

# Restore the full indices.json.
mv "$WDIR/coverage/indices.full.json" "$WDIR/coverage/indices.json"

# Marker for run_matrix_all's cache check — the v2 layout includes the
# panic-locations capture, which the v1 runs don't have.
touch "$OUT_DIR/v2.done"
