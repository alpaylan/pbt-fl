#!/usr/bin/env bash
# validate_haskell_workloads.sh — run `etna experiment run --tests <name>`
# against every Haskell workload that has a tests/<name>.json. Produces a
# per-workload log + aggregated jsonl manifest.
#
# Skips the `semver` test file (Rust workload of the same name owns it).
# Override with VALIDATE_INCLUDE_SEMVER=1 if you've reconciled the conflict.

set -u

FAULTLOC=/Users/akeles/Programming/projects/PbtBenchmark/faultloc
cd "$FAULTLOC"

STAMP=$(date +%Y%m%d-%H%M%S)
RUN_DIR="$FAULTLOC/overnight-logs/haskell-validate-$STAMP"
MANIFEST="$RUN_DIR/runs.jsonl"
mkdir -p "$RUN_DIR"

# Collect every Haskell workload that has both etna.toml and a
# tests/<name>.json — that's the runnable set.
TARGETS=()
for d in "$FAULTLOC"/workloads/Haskell/*/; do
    n=$(basename "$d")
    [ -f "$d/etna.toml" ] || continue
    [ -f "$FAULTLOC/tests/$n.json" ] || continue
    if [ "$n" = "semver" ] && [ "${VALIDATE_INCLUDE_SEMVER:-0}" != "1" ]; then
        echo "[driver] skip semver — colliding with workloads/Rust/semver" >&2
        continue
    fi
    TARGETS+=("$n")
done

echo "[driver] $STAMP — ${#TARGETS[@]} workloads to validate"
echo "[driver] logs: $RUN_DIR"
echo

OK=0
FAILED=0

for name in "${TARGETS[@]}"; do
    log="$RUN_DIR/$name.log"
    ts_start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    start_s=$(date +%s)
    echo "[$name] running"

    # `etna experiment run --tests <name>` runs every entry in tests/<name>.json.
    # Default mode is Solve; the runner records each trial in the etna store.
    if etna experiment run --tests "$name" > "$log" 2>&1; then
        rc=0
        status="ok"
        OK=$((OK+1))
    else
        rc=$?
        status="failed"
        FAILED=$((FAILED+1))
    fi

    elapsed=$(( $(date +%s) - start_s ))
    ts_end=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    printf "[%s] %s (rc=%d, %ds)\n" "$name" "$status" "$rc" "$elapsed"

    printf '{"workload":"%s","status":"%s","rc":%d,"elapsed_s":%d,"log":"%s","ts_start":"%s","ts_end":"%s"}\n' \
        "$name" "$status" "$rc" "$elapsed" "$log" "$ts_start" "$ts_end" \
        >> "$MANIFEST"
done

printf "\n=== summary ===\n  ok: %d\n  failed: %d\n  total: %d\n  manifest: %s\n" \
    "$OK" "$FAILED" "${#TARGETS[@]}" "$MANIFEST"
