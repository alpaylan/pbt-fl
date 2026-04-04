# Workload Generation

This is a design document that describes an LLM-guided pipeline that turns a project into an ETNA workload.

## Scope

- Target: multiple Rust projects that already have property-based tests.
- Goal: 20-50 injected mutations per project.
- Marauders supports multiple languages, but the pipeline targets Rust for now.

## ETNA

[ETNA](http://github.com/alpaylan/etna-cli) is an evaluation platform for property-based testing tools. An ETNA workload is a program injected with
bugs that has corresponding property-based tests that would fail with certain inputs. ETNA uses a
source level mutation framework for injecting mutations in the code, a tool called [marauders](http://github.com/alpaylan/marauders).

### Marauders

#### Comment Syntax

The standard marauders mutation syntax uses comments to annotate variants inline:

```rust
fn add(a: i32, b: i32) -> i32 {
    /*| add [arith, core] */
    a + b
    /*|| add_1 */
    /*|
    a - b
    */
    /*|| add_2 */
    /*|
    a * b
    */
    /* |*/
}
```

#### Functional Mutations

Functional mutations express variants using environment variables and match expressions. Each variant is selected via an environment variable `M_<variant>` set to `active`. If no variant is active, the base branch executes.

```rust
fn add(a: i32, b: i32) -> i32 {
    /* marauders:variation=add;tags=arith,core */
    match () {
        _ if matches!(std::env::var("M_add_1").as_deref(), Ok("active")) => {
            a - b
        },
        _ if matches!(std::env::var("M_add_2").as_deref(), Ok("active")) => {
            a * b
        },
        _ => {
            a + b
        },
    }
}
```

The key benefit is that functional mutations do not require multiple compilation steps — variants are selected at runtime via environment variables. The downside is reduced readability and maintainability due to the intrusive match expressions.

#### Syntax Conversion

Marauders supports converting between mutation syntaxes:

```sh
# Rust-specific conversions
marauders convert --path src/lib.rs --to functional
marauders convert --path src/lib.rs --to comment

# Language-agnostic conversions
marauders convert --path src/lib.rs --to preprocessor
marauders convert --path src/lib.rs --to patch
marauders convert --path src/lib.rs --to match-replace
```

## Implementation

### Architecture

**Claude Code is the outer loop.** Claude Code drives the pipeline — reading code, reasoning about diffs, classifying bugs, generating mutations and tests. A Python tool provides the deterministic scaffolding:

- Git history traversal (batched, 50 commits at a time)
- Marauders command execution
- Cargo test execution
- JSON checkpoint management

Claude Code invokes the Python tool for these mechanical operations and makes all judgment calls directly.

### Pi Agent Layer

To run this as a reusable agent, put a thin orchestration layer on top of `wkgen`:

- `wkgen agent run` orchestrates the full stage sequence and writes checkpoint files.
- `wkgen agent status` reports which stage files exist and the current run state.
- Agent state is persisted as `checkpoints/agent_state.json` with a stable `run_id`.

Backends:

- `--backend dry`: writes placeholder stage outputs to bootstrap a run and verify pipeline wiring.
- `--backend pi`: calls a configurable command template (`--pi-cmd`) once per stage and expects JSON output on stdout.

Default Pi command template:

```sh
python3 -m wkgen agent run \
  --project-dir workloads/Rust/<project> \
  --backend pi \
  --pi-cmd "pi run --json --stage {stage}"
```

The command receives a JSON payload on stdin:

- `run_id`, `project_dir`, `stage`, `stage_guidance`
- `stage_order`
- `context` (all currently available checkpoint JSONs)

It must print valid JSON for that stage; `wkgen` writes it to `checkpoints/<stage>.json` atomically.

### pi-etna CLI

`pi-etna` is a stage-machine runner that can drive the full workload lifecycle incrementally:

```sh
# Full run
./pi-etna run --project-dir workloads/Rust/<project> --backend pi

# Resume only a stage window
./pi-etna resume --project-dir workloads/Rust/<project> --from-stage tests --to-stage validation

# Inspect current run state/checkpoints
./pi-etna status --project-dir workloads/Rust/<project>
```

Robustness rules in `pi-etna`:

- Per-stage retries (`--max-attempts`) with persisted `last_error`.
- Atomic checkpoint writes for every stage.
- Persistent state in `checkpoints/pi_etna_state.json`.
- Deterministic schema checks and gate checks before accepting stage output.

### Git Traversal Strategy

Scan project history in reverse-chronological batches of 50 commits. For each batch:

1. Retrieve commit metadata and diffs.
2. Have Claude Code classify which commits are bug fixes.
3. Process the identified bug fixes through the pipeline.
4. If the mutation target (20-50) is not yet reached, fetch the next batch.

This avoids loading the entire history upfront and allows early stopping.

### Test Execution Strategy

Tests run serially. To avoid recompilation overhead when switching between variants, the pipeline uses **functional mutations**:

1. After injecting mutations in comment syntax (the authoring format), convert to functional syntax:
   `marauders convert --path <file> --to functional`
2. Run tests with different variants by setting environment variables:
   `M_<variant>=active cargo test`
3. No recompilation is needed between variant switches — only the environment variable changes.
4. For the final committed workload, convert back to comment syntax for readability:
   `marauders convert --path <file> --to comment`

### Pipeline Stages and Checkpoints

Each stage produces a JSON artifact that feeds the next. All artifacts are written to a `checkpoints/` directory in the project.

```
candidates.json -> ranked.json -> fixes.json -> classified.json -> tests.json -> mutations.json -> report.json -> docs.json
```

This gives resumability (restart from any stage), inspectability (review before proceeding), and auditability (final report is the composition of all artifacts).

### Consistency and Drift Prevention

To prevent checkpoint/report drift, enforce the following rules:

1. **Single source of truth**: `candidates.json`, `ranked.json`, `fixes.json`, `classified.json`, `tests.json`, and `mutations.json` are authoritative. `report.json` must be generated from these files, not edited manually.
2. **Run identity**: every checkpoint must include the same `run_id` (UUID) and `project` name so artifacts from different runs cannot be mixed.
3. **Deterministic summary fields**: report counters must be computed directly from checkpoint contents (for example, counts from array lengths), never copied from notes or ad-hoc logs.
4. **No duplicated counters without reconciliation**: if a metric appears in multiple files, one file is canonical and all other occurrences must be derived from it.
5. **Publish gate**: generation fails if any cross-file invariant fails (see validation step below). A workload is not considered complete until validation passes.
6. **Detection gate**: a mutation cannot be retained unless at least one regression test fails when the variant is active and passes in base mode.
7. **Property-detector gate**: each retained mutation must have at least one validated failing property-based detector test recorded and published in the docs.

## Injection Algorithm

### Step 1: Identify Bug Fixes

Go through the project history in batches of 50 commits. For each batch, use Claude Code to classify commits, issues, and PRs as bug fixes by analyzing commit messages, issue titles, PR titles, and labels.

A bug fix may span multiple commits or be mixed with unrelated changes. The pipeline should:

- **Isolate the fix**: extract only the bug-fix-related changes from a commit, discarding unrelated refactoring or feature work.
- **Compose multi-commit fixes**: if a fix spans multiple commits (e.g., a fix + follow-up correction), combine them into a single logical fix.

**Checkpoint** (`candidates.json`): produce a ranked candidate list of potential bug fixes to inject.

### Step 2: Filter and Rank Candidates

Not all bug fixes are equally suitable for injection. Rank candidates by:

- **Locality**: prefer small, localized diffs over sweeping changes.
- **Semantic clarity**: prefer bugs with clear, understandable semantics (off-by-one, missing check, wrong operator) over complex behavioral bugs.
- **Testability**: prefer bugs in code that is covered by existing property-based tests.
- **Diversity**: balance mutation types (arithmetic, logical, structural, missing checks) to avoid a homogeneous workload.

**Checkpoint** (`ranked.json`): candidates ordered by suitability.

### Step 3: Extract the Fix

For each candidate, extract the precise code change that constitutes the fix. This means isolating the relevant hunks from the diff, potentially across multiple commits, and producing a clean before/after representation of the buggy vs. fixed code.

**Checkpoint** (`fixes.json`): before/after code pairs for each candidate.

### Step 4: Classify Mutation Difficulty

Before attempting injection, classify each candidate by how well it maps to a marauders mutation:

- **Expression-level** (easy): wrong operator, wrong constant, swapped arguments — maps directly to marauders variant syntax.
- **Statement-level** (medium): missing/extra statement, wrong branch — expressible by wrapping a block in a mutation.
- **Structural** (hard): missing control flow, wrong algorithm, missing feature — may require creative encoding or may not be expressible at all.

Skip or deprioritize candidates that marauders cannot faithfully express. For bugs involving missing code (e.g., a forgotten bounds check), the mutation removes the check in the buggy variant.

**Checkpoint** (`classified.json`): candidates annotated with difficulty and expressibility.

### Step 5: Find Existing Tests / Generate New Tests

This step has two sub-tasks:

#### 5a: Find Existing PBTs

Since we target projects that already have property-based tests, identify which existing PBTs cover the buggy code. These tests should fail on the buggy version and pass on the fixed version. We test against all PBT frameworks the project uses (proptest, quickcheck, crabcheck, and others).

#### 5b: Generate Tests

For each mutation, produce two kinds of tests:

- **Regression test**: a specific, non-parameterized test that reproduces the exact bug with a concrete input. This serves as a reproducibility check — it must always be present.
- **Property-based test**: a parameterized test that captures the property violated by the bug. This is the actual task that PBT tools will be evaluated on — can they find an input that triggers the bug? If existing PBTs already cover the bug, this may just be a reference to them; otherwise, generate a new PBT.

Regression tests are required for acceptance, not only documentation:

- If a candidate mutation is initially undetected, add or strengthen regression tests until the bug is detected, or remove the mutation with an explicit reason.
- `tests.json` must record, per mutation variant, which regression tests were executed and which failed under the active variant.

**Checkpoint** (`tests.json`): test definitions and references for each candidate, including per-variant property-detector candidates and validation outcomes.

### Step 6: Inject Mutation

For each candidate, inject a marauders mutation in comment syntax that recreates the bug. Then convert to functional syntax for verification.

Verify (using functional mutations to avoid recompilation):

- The base (fixed) version compiles and all tests pass: `cargo test`
- The mutated (buggy) version compiles and the relevant tests fail: `M_<variant>=active cargo test`
- Mutations that cause compile errors are discarded — only runtime-observable bugs are committed.
- Mutations that are not detected by at least one regression test are not accepted; either add targeted tests and re-run, or remove the mutation.

After verification, convert back to comment syntax for the final workload:

- `marauders convert --path <file> --to comment`

Use marauders commands to verify mutation detection:

- `marauders list` — confirm the mutation is detected.

**Checkpoint** (`mutations.json`): list of injected and verified mutations.

### Step 7: Produce Report

For each injected mutation, produce a structured report (JSON) containing:

- Mutation name and type (expression/statement/structural).
- Marauders variant name and tags.
- Source commit(s)/issue(s)/PR(s) that the bug was derived from.
- The before/after diff.
- Associated regression test(s) and PBT(s).
- Confidence level and whether human review is recommended (see below).

`report.json` must be generated from checkpoints, with no hand-authored numeric summaries.

**Checkpoint** (`report.json`): the full workload report.

### Step 7.25: Build Property-Detector Mapping and Docs

After final mutations are selected, build a per-variant property-detector map:

- For each retained variant, run focused property-test filters and record at least one failing property test in variant-active mode.
- Prefer specific detectors (targeted property tests) when available; if multiple property tests fail, select one as the canonical detector and record it.
- Keep this mapping synchronized with human-facing docs (`BUGS.md`, `BUGS.html`) by adding a `Failing property test` field per bug plus an index table of variant-to-property-test mappings.

**Checkpoint** (`docs.json`): machine-readable variant-to-property-test mapping used to render documentation tables.

### Step 7.5: Validate Cross-Checkpoint Consistency

Before finalizing, run a strict consistency check that compares all checkpoint files and report fields.

Minimum invariants:

- `report.summary.commits_scanned == candidates.total_commits_scanned` (or report field is omitted if not directly derivable).
- `report.summary.candidates_identified == len(candidates.candidates)`.
- `report.summary.mutations_final == len(report.final_mutations)`.
- Every mutation in `report.final_mutations` exists in `mutations.json` by variant/name.
- Every failing test listed in `report.final_mutations` exists in `tests.json`.
- Every mutation listed as removed in `report.json` has a reason and does not appear in final mutations.
- `report.summary.mutations_undetected == 0` for the finalized workload (or the run must be marked interim).
- Every mutation in `report.final_mutations` has at least one failing regression test recorded in `tests.json`.
- Every mutation in `report.final_mutations` has a canonical failing property test recorded in `docs.json`.
- Every final mutation variant appears in `BUGS.md` and `BUGS.html` with the same canonical failing property test as `docs.json`.

On failure, produce a machine-readable mismatch report and stop the pipeline.

**Checkpoint** (`validation.json`): pass/fail + mismatch details.

### Step 8: Iterate

Repeat steps 1-7.5 (including step 7.25 for property-detector docs, then fetching the next batch of 50 commits) until:

- The target of 20-50 mutations per project is reached, or
- The commit history is exhausted.

Prioritize diversity across mutation types and code regions to produce a representative workload.

## Quality Control

The pipeline uses a 2-tiered review process:

- **Tier 1 (automated)**: Claude Code assesses each injected mutation for faithfulness to the original bug, correct test behavior, and overall quality. High-confidence mutations are accepted automatically.
- **Tier 2 (human review)**: Claude Code flags mutations where it is uncertain — e.g., the mutation is a rough approximation of the original bug, the property is ambiguous, or the test coverage is unclear. These are routed to a human reviewer.

Mutations should be as similar as possible to the original bug. The goal is to recreate real bugs, not arbitrary mutations.

## Dry Run Mode

The pipeline supports a dry-run mode where it identifies candidates, proposes mutations, and generates reports — but does not actually inject any mutations into the codebase. This allows human review of the full plan before committing changes.
