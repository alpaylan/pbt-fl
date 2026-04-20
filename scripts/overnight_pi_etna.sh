#!/usr/bin/env bash
# overnight_pi_etna.sh — drive the pi-etna pipeline over a list of Rust candidates,
# one candidate per `claude -p` headless invocation with a wall-clock cap.
#
# Behaviors:
#   * Skips candidates whose workloads/Rust/<name>/etna.toml already has [[variant]].
#   * Kills any invocation that exceeds its per-candidate cap (returns 124).
#   * Auto-commits on success (workloads/Rust/<name> + tests/<name>.json if present).
#   * Per-candidate log at overnight-logs/<stamp>/<name>.log.
#   * Manifest at overnight-logs/<stamp>/runs.jsonl.

set -u

FAULTLOC=/Users/akeles/Programming/projects/PbtBenchmark/faultloc
cd "$FAULTLOC"

STAMP=$(date +%Y%m%d-%H%M%S)
RUN_DIR="$FAULTLOC/overnight-logs/$STAMP"
MANIFEST="$RUN_DIR/runs.jsonl"
mkdir -p "$RUN_DIR"

# "name:cap_seconds" — cap=3600 for <1000 commits, 7200 for larger.
CANDIDATES=(
  "time:7200"
  "num-bigint:3600"
  "indexmap:3600"
  "rust-decimal:3600"
  "ropey:3600"
  "bstr:3600"
)

# Heredoc — keeps the prompt readable and lets us %-format the path safely.
read -r -d '' PROMPT_TMPL <<'PROMPT' || true
Build an ETNA workload for the Rust project at %s.

Follow the pi-etna pipeline verbatim as described in pi-etna/prompts/run.md and
pi-etna/AGENTS.md. Read both documents first.

RESUME FIRST. Before starting any stage, inspect the project directory for partial
state from an interrupted prior run:
  - progress.jsonl — if it exists, read it tail-first. The last event tells you
    which stage/variant you were in when the run stopped. Resume from there;
    do not redo completed stages or re-process variants whose
    `variant_committed` event is already logged.
  - etna.toml — each `[[variant]]` entry is a completed atomize iteration. Skip
    those candidates in atomize.
  - etna/* branches (git branch --list 'etna/*') — these are per-variant
    commits. If a branch exists and its variant is in etna.toml, treat the
    variant as complete.
  - patches/*.patch — each corresponds to a patch-injection variant. Same
    rule: if its name is in etna.toml, skip.
  - src/bin/etna.rs, BUGS.md, TASKS.md — if these exist and are coherent with
    etna.toml, treat the runner/document stages as done; only re-enter them if
    etna.toml changed after they were written.
When resuming, append progress events with the current timestamp so the log
shows both runs contiguously. Never rewrite or truncate progress.jsonl.
If nothing partial exists, this is a fresh run — proceed normally from discover.

Work through all five stages end-to-end: discover, atomize, runner, document,
validate. Do not stop at the first passing build — every bug-fix commit in the
target's history becomes a variant unless terminally inexpressible.

Stay inside the candidate directory for all file edits; do not touch other workloads or
unrelated repos. Use the standard marauders/git operations (commit per variant on
etna/<variant> branches).

This is an unattended overnight run. Do not ask clarifying questions. Make reasonable
defaults and proceed.

When validate passes on base + every variant + every framework, print on its own line at
the very end:

PI_ETNA_DONE variants=<N> tasks=<M>

If the workload cannot be built — for any reason — print on its own line at the very end:

PI_ETNA_ABANDON reason=<short description>
PROMPT

run_with_cap() {
    # Usage: run_with_cap <cap_seconds> <command ...>
    # Returns the command's exit code, or 124 if the cap fired.
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
    [ -f "$path/etna.toml" ] && grep -q '^\[\[variant\]\]' "$path/etna.toml"
}

extract_counts() {
    # Parse "PI_ETNA_DONE variants=N tasks=M" (or the ABANDON variant's reason) out of a log.
    local log=$1
    awk '
        /PI_ETNA_DONE/ { for (i=1; i<=NF; i++) if ($i ~ /^variants=|^tasks=/) print $i; exit }
        /PI_ETNA_ABANDON/ { sub(/^.*PI_ETNA_ABANDON /, "abandon="); print; exit }
    ' "$log"
}

progress_success() {
    # True if progress.jsonl has a validate.all_checks_passed event.
    # This is a more reliable "run succeeded" signal than stdout scanning,
    # because progress events are fsync'd to the file as they occur while
    # claude -p's stdout is full-buffered when redirected and loses buffers
    # on SIGTERM at cap-time.
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
    name="${entry%:*}"
    cap="${entry#*:}"
    path="$FAULTLOC/workloads/Rust/$name"
    log="$RUN_DIR/$name.log"
    ts_start=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    if [ ! -d "$path" ]; then
        printf "[%s] skip — no such workload dir\n" "$name"
        printf '{"candidate":%s,"status":"skipped","reason":"no dir","ts_start":%s}\n' \
            "$(json_str "$name")" "$(json_str "$ts_start")" >> "$MANIFEST"
        SKIPPED=$((SKIPPED+1))
        continue
    fi

    if already_done "$path"; then
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

    # Classification order matters:
    # 1. progress.jsonl with validate.all_checks_passed wins over everything —
    #    a timed-out run that actually finished is still a successful run
    #    (claude -p may hold its stdout buffer past the SIGTERM, so log-grep
    #    alone misses late-flushed success markers).
    # 2. Otherwise fall back to rc + stdout markers.
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
        git add "workloads/Rust/$name" >> "$log" 2>&1
        if [ -f "tests/$name.json" ]; then
            git add "tests/$name.json" >> "$log" 2>&1
        fi
        if git commit -m "pi-etna: add $name workload (overnight $STAMP)" \
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
