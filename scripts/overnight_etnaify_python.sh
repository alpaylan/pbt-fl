#!/usr/bin/env bash
# overnight_etnaify_python.sh — drive the etna-ify pipeline over a list of
# Python candidates, one candidate per `claude -p` headless invocation with
# a wall-clock cap.
#
# Sibling of overnight_etnaify.sh (Rust). Differences:
#   * Targets workloads/Python/<name> (not /Rust/).
#   * Uses etna-ify/prompts/run-python.md (Hypothesis + CrossHair backends).
#   * Resume detection looks at progress.jsonl tail just like Rust.
#   * Uses scripts/check_python_workload.py for the success-classification
#     post-condition when progress.jsonl is missing the all_checks_passed
#     event but etna.toml looks plausible.
#
# Behaviors:
#   * Skips candidates whose workloads/Python/<name>/etna.toml already has [[tasks]].
#   * Kills any invocation that exceeds its per-candidate cap (returns 124).
#   * Auto-commits on success (workloads/Python/<name>).
#   * Per-candidate log at overnight-logs/<stamp>/<name>.log.
#   * Manifest at overnight-logs/<stamp>/runs.jsonl.

set -u

FAULTLOC=/Users/akeles/Programming/projects/PbtBenchmark/faultloc
cd "$FAULTLOC"

STAMP=$(date +%Y%m%d-%H%M%S)
RUN_DIR="$FAULTLOC/overnight-logs/python-$STAMP"
MANIFEST="$RUN_DIR/runs.jsonl"
mkdir -p "$RUN_DIR"

# "name:cap_seconds[:force]" — cap budget tuned to history size and
# expected CrossHair friction. Append ":force" to bypass the already_done
# skip check (resume into a partially-completed workload).
#
# Order is execution order: cheap, high-confidence wins first so a partial
# overnight still produces something; expensive stretch goals last.
CANDIDATES=(
  # A-tier — pure python, classic invariants, expect 5-15 variants each.
  "sortedcontainers:3600"
  "bidict:3600"
  "boltons:5400"
  "toolz:5400"
  "more-itertools:5400"
  "funcy:5400"

  # B-tier — pure python but more parser/text-shaped; CrossHair may
  # selectively time out on individual variants (acceptable, see prompt).
  "python-slugify:3600"
  "iso8601:3600"
  "humanize:3600"
  "inflect:5400"
)

# CANDIDATE_REPOS — upstream URL for `git clone` when scaffolding a new
# workload. Only consulted if workloads/Python/<name>/.git is missing.
declare -A CANDIDATE_REPOS=(
  ["sortedcontainers"]="https://github.com/grantjenks/python-sortedcontainers"
  ["bidict"]="https://github.com/jab/bidict"
  ["boltons"]="https://github.com/mahmoud/boltons"
  ["toolz"]="https://github.com/pytoolz/toolz"
  ["more-itertools"]="https://github.com/more-itertools/more-itertools"
  ["funcy"]="https://github.com/Suor/funcy"
  ["python-slugify"]="https://github.com/un33k/python-slugify"
  ["iso8601"]="https://github.com/micktwomey/pyiso8601"
  ["humanize"]="https://github.com/python-humanize/humanize"
  ["inflect"]="https://github.com/jaraco/inflect"
)

read -r -d '' PROMPT_TMPL <<'PROMPT' || true
Build an ETNA workload for the Python project at %s.

Follow the etna-ify pipeline verbatim as described in
etna-ify/prompts/run-python.md and etna-ify/AGENTS.md. Read both documents
first.

RESUME FIRST. Before starting any stage, inspect the project directory for
partial state from an interrupted prior run:
  - progress.jsonl — if it exists, read it tail-first. The last event tells
    you which stage/variant you were in when the run stopped. Resume from
    there; do not redo completed stages or re-process variants whose
    `variant_committed` event is already logged.
  - etna.toml — each `[[tasks]]` group is a completed atomize iteration.
    Skip those candidates in atomize.
  - patches/*.patch — each corresponds to a patch-injection variant. If its
    name is in etna.toml, skip.
  - etna/properties.py, etna/strategies.py, etna/witnesses.py,
    etna/runner.py — if these exist and are coherent with etna.toml, treat
    the runner stage as done; only re-enter it if etna.toml changed after
    they were written.
When resuming, append progress events with the current timestamp so the
log shows both runs contiguously. Never rewrite or truncate progress.jsonl.
If nothing partial exists, this is a fresh run — proceed normally from
discover.

EXTEND MODE. If progress.jsonl already contains
`validate.all_checks_passed`, the workload is technically complete but may
be under-mined — the prior run may have capped out before traversing the
full git history. Do not exit early. Re-run discover across the full
history, compare the candidate list against the variants already in
etna.toml, and atomize every missing candidate. The existing variants are
frozen; only add new ones. Run document + validate at the end so the docs
and the detection matrix reflect the expanded variant set.

Work through all five stages end-to-end: discover, atomize, runner,
document, validate. Do not stop at the first passing build — every
bug-fix commit in the target's history becomes a variant unless terminally
inexpressible (or non-CrossHair-able for the whole library; see
run-python.md for the bucket-3 drop rule).

Stay inside the candidate directory for all file edits; do not touch other
workloads or unrelated repos. Use `patches/<variant>.patch` for mutation
injection — patches only, no marauders, no per-variant git branches.

This is an unattended overnight run. Do not ask clarifying questions. Make
reasonable defaults and proceed.

When validate passes on base + every variant + both backends (allowing
CrossHair timeouts annotated per-variant), print on its own line at the
very end:

PI_ETNA_DONE variants=<N> tasks=<M>

If the workload cannot be built — for any reason — print on its own line at
the very end:

PI_ETNA_ABANDON reason=<short description>
PROMPT

run_with_cap() {
    local cap=$1; shift
    local flag
    flag=$(mktemp)
    "$@" &
    local pid=$!
    (
        sleep "$cap"
        if kill -0 "$pid" 2>/dev/null; then
            echo timeout > "$flag"
            kill -TERM "$pid" 2>/dev/null
            sleep 30
            kill -KILL "$pid" 2>/dev/null
        fi
    ) &
    local watchdog=$!
    wait "$pid" 2>/dev/null
    local rc=$?
    kill -TERM "$watchdog" 2>/dev/null
    wait "$watchdog" 2>/dev/null
    if [ "$(cat "$flag" 2>/dev/null)" = "timeout" ]; then
        rm -f "$flag"
        return 124
    fi
    rm -f "$flag"
    return "$rc"
}

json_str() {
    python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$1"
}

already_done() {
    local path=$1
    [ -f "$path/etna.toml" ] && grep -q '^\[\[tasks\]\]' "$path/etna.toml"
}

ensure_workload_dir() {
    # If workloads/Python/<name>/.git is missing, clone the upstream into
    # place. This is the only network-touching step; do it once before
    # claude -p starts so the agent doesn't have to do it.
    local name=$1 path=$2
    if [ -d "$path/.git" ]; then
        return 0
    fi
    local repo="${CANDIDATE_REPOS[$name]:-}"
    if [ -z "$repo" ]; then
        echo "[$name] no upstream URL in CANDIDATE_REPOS — cannot clone" >&2
        return 1
    fi
    mkdir -p "$(dirname "$path")"
    if ! git clone "$repo" "$path" 2>&1 | head -5; then
        echo "[$name] clone failed" >&2
        return 1
    fi
}

extract_counts() {
    local log=$1
    awk '
        /PI_ETNA_DONE/ { for (i=1; i<=NF; i++) if ($i ~ /^variants=|^tasks=/) print $i; exit }
        /PI_ETNA_ABANDON/ { sub(/^.*PI_ETNA_ABANDON /, "abandon="); print; exit }
    ' "$log"
}

progress_success() {
    local proj=$1
    [ -f "$proj/progress.jsonl" ] || return 1
    grep -q '"stage":"validate","event":"all_checks_passed"' "$proj/progress.jsonl"
}

OK=0
FAILED=0
TIMEOUT_COUNT=0
SKIPPED=0

trap 'echo "[driver] interrupted — exiting"; exit 130' INT TERM

printf "[driver] started %s\n[driver] logs: %s\n\n" "$STAMP" "$RUN_DIR"

for entry in "${CANDIDATES[@]}"; do
    IFS=':' read -r name cap force <<< "$entry"
    path="$FAULTLOC/workloads/Python/$name"
    log="$RUN_DIR/$name.log"
    ts_start=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    if ! ensure_workload_dir "$name" "$path"; then
        printf "[%s] skip — workload dir setup failed\n" "$name"
        printf '{"candidate":%s,"status":"skipped","reason":"no dir","ts_start":%s}\n' \
            "$(json_str "$name")" "$(json_str "$ts_start")" >> "$MANIFEST"
        SKIPPED=$((SKIPPED+1))
        continue
    fi

    if [ "$force" != "force" ] && already_done "$path"; then
        printf "[%s] skip — etna.toml already populated\n" "$name"
        printf '{"candidate":%s,"status":"skipped","reason":"already done","ts_start":%s}\n' \
            "$(json_str "$name")" "$(json_str "$ts_start")" >> "$MANIFEST"
        SKIPPED=$((SKIPPED+1))
        continue
    fi

    printf "[%s] running (cap=%ss)\n" "$name" "$cap"
    # shellcheck disable=SC2059
    prompt=$(printf "$PROMPT_TMPL" "$path")
    start_s=$(date +%s)

    run_with_cap "$cap" bash -c \
        'claude -p --dangerously-skip-permissions "$1" > "$2" 2>&1' \
        _ "$prompt" "$log"
    rc=$?

    elapsed=$(( $(date +%s) - start_s ))
    ts_end=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    counts=$(extract_counts "$log" | tr '\n' ' ' | sed 's/ *$//')

    # Classification (mirror Rust driver):
    # 1. progress.jsonl with validate.all_checks_passed wins.
    # 2. else rc=124 → timeout.
    # 3. else rc!=0 → failed.
    # 4. else PI_ETNA_DONE in log → ok.
    # 5. else PI_ETNA_ABANDON → abandoned.
    # 6. else unclear.
    if progress_success "$path"; then
        status="ok"
        OK=$((OK+1))
    elif [ "$rc" -eq 124 ]; then
        status="timeout"
        TIMEOUT_COUNT=$((TIMEOUT_COUNT+1))
    elif [ "$rc" -ne 0 ]; then
        status="failed"
        FAILED=$((FAILED+1))
    elif grep -q 'PI_ETNA_DONE' "$log"; then
        status="ok"
        OK=$((OK+1))
    elif grep -q 'PI_ETNA_ABANDON' "$log"; then
        status="abandoned"
        FAILED=$((FAILED+1))
    else
        status="unclear"
        FAILED=$((FAILED+1))
    fi

    printf "[%s] %s (rc=%d, %ds) %s\n" "$name" "$status" "$rc" "$elapsed" "$counts"

    if [ "$status" = "ok" ]; then
        git add "workloads/Python/$name" >> "$log" 2>&1
        if git commit -m "etna-ify: add $name workload (overnight $STAMP)" \
                      -m "Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>" \
                      >> "$log" 2>&1; then
            printf "[%s] committed\n" "$name"
        else
            printf "[%s] commit failed — inspect %s\n" "$name" "$log" >&2
        fi
    fi

    printf '{"candidate":%s,"status":%s,"rc":%d,"elapsed_s":%d,"counts":%s,"log":%s,"ts_start":%s,"ts_end":%s}\n' \
        "$(json_str "$name")" "$(json_str "$status")" "$rc" "$elapsed" \
        "$(json_str "$counts")" "$(json_str "$log")" \
        "$(json_str "$ts_start")" "$(json_str "$ts_end")" \
        >> "$MANIFEST"
done

printf "\n=== summary ===\n  ok: %d\n  timeout: %d\n  failed/abandoned/unclear: %d\n  skipped: %d\n  manifest: %s\n" \
    "$OK" "$TIMEOUT_COUNT" "$FAILED" "$SKIPPED" "$MANIFEST"
