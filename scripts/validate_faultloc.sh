#!/bin/bash
# Run one faultloc validation cycle for a workload+variant.
#
# Usage:
#   validate_faultloc.sh <workload> <property> <short_name> <kind:arg> <tests> [extra_features]
#     kind:arg may be:
#       patch:<path>         — `git apply <path>` (with whitespace / -C0 fallbacks)
#       marauders:<variant>  — `marauders set --variant <variant>`

set -euo pipefail

WORKLOAD="${1:?workload name}"
PROPERTY="${2:?property name}"
SHORT_NAME="${3:?short_name for result dir}"
KIND_ARG="${4:?kind:arg (patch:<path> | marauders:<variant>)}"
TESTS="${5:-100}"
EXTRA_FEATURES="${6:-}"

KIND="${KIND_ARG%%:*}"
ARG="${KIND_ARG#*:}"

ROOT=/Users/akeles/Programming/projects/PbtBenchmark/faultloc
WDIR="$ROOT/workloads/Rust/$WORKLOAD"
RESULTS_DIR="$ROOT/faultloc-results/$WORKLOAD/$SHORT_NAME"
MARAUDER_BACKUP="/tmp/mime_marauder_backup_$$.tar"

mkdir -p "$RESULTS_DIR"

cleanup() {
  case "$KIND" in
    patch)
      (cd "$WDIR" && (git apply -R --ignore-whitespace "$ARG" 2>/dev/null || git apply -R -C0 --ignore-whitespace "$ARG" 2>/dev/null)) || true
      ;;
    marauders)
      if [ -f "$MARAUDER_BACKUP" ]; then
        (cd "$WDIR" && tar -xf "$MARAUDER_BACKUP")
        rm -f "$MARAUDER_BACKUP"
      fi
      ;;
  esac
}
trap cleanup EXIT

case "$KIND" in
  patch)
    echo "[$WORKLOAD/$SHORT_NAME] applying patch $ARG"
    (cd "$WDIR" && (git apply --ignore-whitespace "$ARG" 2>/dev/null || git apply -C0 --ignore-whitespace "$ARG"))
    ;;
  marauders)
    # Back up the files that marauders will modify (listed by `marauders list`)
    # so we can restore them reliably, since `marauders unset` sometimes fails
    # after `marauders set` (known issue).
    FILES_TO_BACKUP=$(cd "$WDIR" && marauders list 2>/dev/null | grep -E "variants: \[\"$ARG\"\]" | sed 's|:.*||' | head -1)
    if [ -z "$FILES_TO_BACKUP" ]; then
      echo "ERROR: marauders list did not find variant $ARG in $WDIR" >&2
      exit 1
    fi
    (cd "$WDIR" && tar -cf "$MARAUDER_BACKUP" $FILES_TO_BACKUP)
    echo "[$WORKLOAD/$SHORT_NAME] activating marauder variant $ARG (file: $FILES_TO_BACKUP)"
    (cd "$WDIR" && marauders set --variant "$ARG")
    ;;
  *)
    echo "Unknown kind: $KIND"; exit 2
    ;;
esac

echo "[$WORKLOAD/$SHORT_NAME] rebuilding with mutation + coverage"
FEATURE_ARGS=""
if [ -n "$EXTRA_FEATURES" ]; then
  FEATURE_ARGS="--features $EXTRA_FEATURES"
fi
(cd "$WDIR" && \
  CARGO_INCREMENTAL=0 \
  RUSTFLAGS="-C instrument-coverage -C link-dead-code -C codegen-units=1 -C inline-threshold=0 -C llvm-args=-inline-threshold=0 -C debuginfo=2" \
  cargo build --release --bin etna-faultloc $FEATURE_ARGS 2>&1 | tail -3)

echo "[$WORKLOAD/$SHORT_NAME] wiping coverage"
rm -rf "$WDIR/coverage" "$WDIR/profdata" "$WDIR/jsondata"
mkdir -p "$WDIR/coverage"

MODULE=$(grep -oE 'fast-analyze coverage [a-z_]+' "$WDIR/steps.sh" | head -1 | awk '{print $3}')

echo "[$WORKLOAD/$SHORT_NAME] running N=$TESTS mutations (module=$MODULE)"
(cd "$WDIR" && \
  CRABCHECK_PROFILING_MUTATIONS=$TESTS \
  LLVM_PROFILE_FILE="coverage/snapshot_%p-%m.profraw" \
  ./target/release/etna-faultloc crabcheck "$PROPERTY" "$TESTS")

echo "[$WORKLOAD/$SHORT_NAME] analysing"
(cd "$WDIR" && \
  crabcheck-profiling-fast-analyze coverage "$MODULE" ./target/release/etna-faultloc --print-json \
    > "$RESULTS_DIR/single-trial-N$TESTS.json")

echo "=== top-10 by delta ==="
jq -r '.regions | sort_by(-.delta) | .[0:10] | map([.delta, .suspiciousness.ochiai, .function, "\(.file):\(.start_line)"] | @tsv) | .[]' "$RESULTS_DIR/single-trial-N$TESTS.json"
echo
echo "=== top-10 by ochiai ==="
jq -r '.regions | sort_by(-.suspiciousness.ochiai) | .[0:10] | map([.suspiciousness.ochiai, .delta, .function, "\(.file):\(.start_line)"] | @tsv) | .[]' "$RESULTS_DIR/single-trial-N$TESTS.json"
echo
echo "positive_samples=$(jq .positive_samples "$RESULTS_DIR/single-trial-N$TESTS.json"), negative_samples=$(jq .negative_samples "$RESULTS_DIR/single-trial-N$TESTS.json")"
