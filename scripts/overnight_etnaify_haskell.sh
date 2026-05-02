#!/usr/bin/env bash
# overnight_etnaify_haskell.sh — drive the etna-ify pipeline over a list of
# Haskell candidates, one candidate per `claude -p` headless invocation with
# a wall-clock cap.
#
# Sibling of overnight_etnaify.sh (Rust) and overnight_etnaify_python.sh.
# Differences from Python:
#   * Targets workloads/Haskell/<name>.
#   * Uses etna-ify/prompts/run-haskell.md (QuickCheck + Hedgehog + Falsify
#     + SmallCheck backends).
#   * Pre-flights GHC 9.6.6 via ghcup (falsify needs base >= 4.18). Installs
#     it if missing.
#   * Uses scripts/check_haskell_workload.py for the success-classification
#     fallback when progress.jsonl is missing the all_checks_passed event
#     but etna.toml looks plausible.
#   * Candidate list is parser/serializer-skewed — utility libs are
#     dominated by CI/build "Fix" commits and rarely yield substantive
#     variants (see project_haskell_workload_candidates memory).
#
# Behaviors:
#   * Skips candidates whose workloads/Haskell/<name>/etna.toml already has [[tasks]].
#   * Kills any invocation that exceeds its per-candidate cap (returns 124).
#   * Auto-commits on success (workloads/Haskell/<name>).
#   * Per-candidate log at overnight-logs/haskell-<stamp>/<name>.log.
#   * Manifest at overnight-logs/haskell-<stamp>/runs.jsonl.

set -u

FAULTLOC=/Users/akeles/Programming/projects/PbtBenchmark/faultloc
cd "$FAULTLOC"

STAMP=$(date +%Y%m%d-%H%M%S)
RUN_DIR="$FAULTLOC/overnight-logs/haskell-$STAMP"
MANIFEST="$RUN_DIR/runs.jsonl"
mkdir -p "$RUN_DIR"

# Required GHC for the runner (falsify needs base >= 4.18 = GHC >= 9.6).
REQUIRED_GHC=9.6.6

# "name:cap_seconds[:force]" — cap budget tuned to history size and expected
# build cost. Append ":force" to bypass the already_done skip check.
#
# Order is execution order: cheap, high-confidence wins first so a partial
# overnight still produces something; expensive stretch goals last.
#
# Already-pre-seeded workloads (pretty-simple, aeson) are intentionally
# omitted — `already_done` would skip them anyway. Add them with `:force`
# if you want the agent to EXTEND-mode their variant set.
CANDIDATES=(
  # A-tier — small, focused, pure parsers / serializers / data-structures
  # with known correctness-fix history. Cap 3600s (1h) per candidate
  # is enough for discover + atomize + runner + validate on a
  # few-hundred-commit history.
  "network-uri:3600"        # URI parser
  "semver:3600"             # SemVer parser
  "uri-bytestring:3600"     # alternative URI parser
  "hashable:3600"           # hash invariants
  "scientific:3600"         # arbitrary-precision numbers
  "chimera:3600"            # lazy infinite streams with O(1) indexing
  "split:3600"              # list splitting
  "tagsoup:3600"            # lenient HTML parser
  "psqueues:3600"           # pure priority queues
  "algebraic-graphs:3600"   # pure graph library
  "cassava:3600"            # CSV parser
  "pretty-show:3600"        # pretty-printer
  "prettyprinter:3600"      # modern pretty-printer
  "mod:3600"                # modular arithmetic
  "email-validate:3600"     # email-address validation

  # Data structures (extra batch; all pure, all A-tier).
  "dlist:3600"              # difference lists
  "bitvec:3600"             # bit vectors
  "pqueue:3600"             # priority queues (alternative to psqueues)
  "bytestring-trie:3600"    # bytestring tries
  "MemoTrie:3600"           # memoization tries
  "nonempty-containers:3600" # non-empty maps / sets
)

# CANDIDATE_REPOS — upstream URL for `git clone` when scaffolding a new
# workload. Only consulted if workloads/Haskell/<name>/.git is missing.
declare -A CANDIDATE_REPOS=(
  ["network-uri"]="https://github.com/haskell/network-uri"
  ["semver"]="https://github.com/brendanhay/semver"
  ["uri-bytestring"]="https://github.com/Soostone/uri-bytestring"
  ["hashable"]="https://github.com/haskell-unordered-containers/hashable"
  ["scientific"]="https://github.com/basvandijk/scientific"
  ["chimera"]="https://github.com/Bodigrim/chimera"
  ["split"]="https://github.com/byorgey/split"
  ["tagsoup"]="https://github.com/ndmitchell/tagsoup"
  ["psqueues"]="https://github.com/jaspervdj/psqueues"
  ["algebraic-graphs"]="https://github.com/snowleopard/alga"
  ["cassava"]="https://github.com/haskell-hvr/cassava"
  ["pretty-show"]="https://github.com/yav/pretty-show"
  ["prettyprinter"]="https://github.com/quchen/prettyprinter"
  ["mod"]="https://github.com/Bodigrim/mod"
  ["email-validate"]="https://github.com/Porges/email-validate-hs"
  ["dlist"]="https://github.com/spl/dlist"
  ["bitvec"]="https://github.com/Bodigrim/bitvec"
  ["pqueue"]="https://github.com/lspitzner/pqueue"
  ["bytestring-trie"]="https://github.com/wrengr/bytestring-trie"
  ["MemoTrie"]="https://github.com/conal/MemoTrie"
  ["nonempty-containers"]="https://github.com/mstksg/nonempty-containers"
)

read -r -d '' PROMPT_TMPL <<'PROMPT' || true
Build an ETNA workload for the Haskell project at %s.

Follow the etna-ify pipeline verbatim as described in
etna-ify/prompts/run-haskell.md and etna-ify/AGENTS.md. Read both documents
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
  - etna/src/Etna/Properties.hs, etna/src/Etna/Witnesses.hs,
    etna/src/Etna/Gens/{QuickCheck,Hedgehog,Falsify,SmallCheck}.hs,
    etna/app/Main.hs — if these exist and are coherent with etna.toml, treat
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

GHC TOOLCHAIN. The driver has pre-installed GHC %s via ghcup and points
the runner at it via cabal.project's `with-compiler`. Do not bump the GHC
version. Falsify >= 0.2 requires base >= 4.18, which is why >= 9.6 is
mandatory.

MONOREPO HANDLING. If the project is a monorepo (e.g. aeson ships
text-iso8601, attoparsec-aeson, attoparsec-iso8601 as sibling packages),
narrow the workload's cabal.project to just the sub-package you're
testing plus etna/. Do not build all sub-packages — pick the most
PBT-amenable one and target it. Document the choice in the workload's
README.etna.md.

CANDIDATE-LIBRARY GUARDRAIL. If on inspection the candidate's git history
is dominated by CI / build / haddock / GHC-compat fixes (see the discover
filter rules in run-haskell.md and the project_haskell_workload_candidates
memory), abandon the run — printing the abandonment line below — rather
than synthesizing variants. The pipeline's value comes from real
historical bugs, not invented ones.

Work through all five stages end-to-end: discover, atomize, runner,
document, validate. Do not stop at the first passing build — every
bug-fix commit in the target's history becomes a variant unless terminally
inexpressible (or non-FFI-able for unsafePerformIO/ForeignPtr-heavy
sub-paths; drop those per run-haskell.md guidance).

Stay inside the candidate directory for all file edits; do not touch other
workloads or unrelated repos. Use `patches/<variant>.patch` for mutation
injection — patches only, no marauders, no per-variant git branches.

This is an unattended overnight run. Do not ask clarifying questions. Make
reasonable defaults and proceed.

When validate passes on base + every variant + all four backends (allowing
SmallCheck timeouts annotated per-variant), print on its own line at the
very end:

PI_ETNA_DONE variants=<N> tasks=<M>

If the workload cannot be built — for any reason — print on its own line at
the very end:

PI_ETNA_ABANDON reason=<short description>
PROMPT

ensure_ghc() {
    if ! command -v ghcup >/dev/null 2>&1; then
        echo "[driver] ghcup not on PATH — install ghcup before running this script." >&2
        return 1
    fi
    if [ ! -x "$(ghcup whereis ghc "$REQUIRED_GHC" 2>/dev/null)" ]; then
        printf "[driver] installing GHC %s via ghcup (one-time, ~3 min)\n" "$REQUIRED_GHC"
        if ! ghcup install ghc "$REQUIRED_GHC" >>"$RUN_DIR/ghcup-install.log" 2>&1; then
            echo "[driver] ghcup install ghc $REQUIRED_GHC failed — see $RUN_DIR/ghcup-install.log" >&2
            return 1
        fi
    fi
    GHC_PATH="$(ghcup whereis ghc "$REQUIRED_GHC")"
    printf "[driver] using GHC %s at %s\n" "$REQUIRED_GHC" "$GHC_PATH"
}

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
    # If workloads/Haskell/<name>/.git is missing, clone the upstream into
    # place. This is the only network-touching step before claude -p starts.
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

# Pre-flight: ensure required GHC is available before any candidate runs.
# This is a one-time install; subsequent invocations skip past it fast.
if ! ensure_ghc; then
    echo "[driver] aborting — GHC pre-flight failed" >&2
    exit 1
fi

for entry in "${CANDIDATES[@]}"; do
    IFS=':' read -r name cap force <<< "$entry"
    path="$FAULTLOC/workloads/Haskell/$name"
    log="$RUN_DIR/$name.log"
    ts_start=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    if ! ensure_workload_dir "$name" "$path"; then
        printf "[%s] skip — workload dir setup failed\n" "$name"
        printf '{"candidate":%s,"status":"skipped","reason":"no dir","ts_start":%s}\n' \
            "$(json_str "$name")" "$(json_str "$ts_start")" >> "$MANIFEST"
        SKIPPED=$((SKIPPED+1))
        continue
    fi

    if [ "${force:-}" != "force" ] && already_done "$path"; then
        printf "[%s] skip — etna.toml already populated\n" "$name"
        printf '{"candidate":%s,"status":"skipped","reason":"already done","ts_start":%s}\n' \
            "$(json_str "$name")" "$(json_str "$ts_start")" >> "$MANIFEST"
        SKIPPED=$((SKIPPED+1))
        continue
    fi

    printf "[%s] running (cap=%ss)\n" "$name" "$cap"
    # shellcheck disable=SC2059
    prompt=$(printf "$PROMPT_TMPL" "$path" "$REQUIRED_GHC")
    start_s=$(date +%s)

    run_with_cap "$cap" bash -c \
        'claude -p --dangerously-skip-permissions "$1" > "$2" 2>&1' \
        _ "$prompt" "$log"
    rc=$?

    elapsed=$(( $(date +%s) - start_s ))
    ts_end=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    counts=$(extract_counts "$log" | tr '\n' ' ' | sed 's/ *$//')

    # Classification (mirror Python/Rust drivers):
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
        # The workload's own .git tracks the upstream files plus our scaffold.
        # We commit inside the workload (not at faultloc/), mirroring the
        # Python overnight pattern.
        (
            cd "$path" || exit 1
            git add -A >> "$log" 2>&1
            if git diff --cached --quiet; then
                printf "[%s] nothing to commit\n" "$name"
            elif git commit -m "etna-ify: add $name workload (overnight $STAMP)" \
                            -m "QuickCheck + Hedgehog + Falsify + SmallCheck backends." \
                            -m "Generated by etna-ify (etna-ify/prompts/run-haskell.md)." \
                            -m "Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>" \
                            >> "$log" 2>&1; then
                printf "[%s] committed\n" "$name"
            else
                printf "[%s] commit failed — inspect %s\n" "$name" "$log" >&2
            fi
        )
    fi

    printf '{"candidate":%s,"status":%s,"rc":%d,"elapsed_s":%d,"counts":%s,"log":%s,"ts_start":%s,"ts_end":%s}\n' \
        "$(json_str "$name")" "$(json_str "$status")" "$rc" "$elapsed" \
        "$(json_str "$counts")" "$(json_str "$log")" \
        "$(json_str "$ts_start")" "$(json_str "$ts_end")" \
        >> "$MANIFEST"
done

printf "\n=== summary ===\n  ok: %d\n  timeout: %d\n  failed/abandoned/unclear: %d\n  skipped: %d\n  manifest: %s\n" \
    "$OK" "$TIMEOUT_COUNT" "$FAILED" "$SKIPPED" "$MANIFEST"
