#!/bin/bash
# Driver: run validate_faultloc_matrix.sh for every job in matrix_jobs.tsv.
#
# Resumable: if all 6 config files exist in the output dir, the job is skipped.
# Logs each job's stdout/stderr to log/matrix-<workload>-<short>.log.
#
# Usage:
#   run_matrix_all.sh [--dry-run] [--from <N>] [--to <M>] [--filter <regex>]

set -uo pipefail

ROOT=/Users/akeles/Programming/projects/PbtBenchmark/faultloc
JOBS_TSV="$ROOT/scripts/matrix_jobs.tsv"
LOG_DIR="$ROOT/scripts/log"
mkdir -p "$LOG_DIR"

DRY_RUN=0
FROM=1
TO=999999
FILTER=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --from) FROM="$2"; shift 2 ;;
    --to) TO="$2"; shift 2 ;;
    --filter) FILTER="$2"; shift 2 ;;
    *) echo "Unknown: $1"; exit 2 ;;
  esac
done

CONFIG_FILES=("N100-with.json" "N100-without.json" "N500-with.json" "N500-without.json" "N1000-with.json" "N1000-without.json")

# v2 layout requires the marker the runner writes after also capturing
# panic_locations.jsonl. v1 runs lack the marker and will re-run.
is_done() {
  local dir="$1"
  [ -e "$dir/v2.done" ] || return 1
  for f in "${CONFIG_FILES[@]}"; do
    [ -s "$dir/$f" ] || return 1
  done
  return 0
}

i=0
n_done=0
n_skipped=0
n_run=0
n_failed=0

# Skip header
tail -n +2 "$JOBS_TSV" | while IFS=$'\t' read -r workload property short kind_arg extra_features; do
  i=$((i + 1))
  [ $i -lt "$FROM" ] && continue
  [ $i -gt "$TO" ] && break
  if [ -n "$FILTER" ] && ! echo "$workload/$short" | grep -qE "$FILTER"; then
    continue
  fi
  out_dir="$ROOT/faultloc-results/$workload/$short/matrix-N1000"
  log_file="$LOG_DIR/matrix-${workload}-${short}.log"

  if is_done "$out_dir"; then
    echo "[$i] $workload/$short — DONE (cached)"
    n_done=$((n_done + 1))
    continue
  fi

  if [ $DRY_RUN -eq 1 ]; then
    echo "[$i] DRY: $workload/$short ($kind_arg)"
    continue
  fi

  echo "[$i] $workload/$short — running ..."
  start=$(date +%s)
  if bash "$ROOT/scripts/validate_faultloc_matrix.sh" \
    "$workload" "$property" "$short" "$kind_arg" "$extra_features" \
    > "$log_file" 2>&1; then
    elapsed=$(($(date +%s) - start))
    if is_done "$out_dir"; then
      echo "    OK ($elapsed s)"
      n_run=$((n_run + 1))
    else
      echo "    PARTIAL ($elapsed s) — see $log_file"
      n_failed=$((n_failed + 1))
    fi
  else
    elapsed=$(($(date +%s) - start))
    echo "    FAIL ($elapsed s) — see $log_file"
    n_failed=$((n_failed + 1))
  fi
done

echo
echo "Summary: cached=$n_done ran=$n_run failed=$n_failed"
