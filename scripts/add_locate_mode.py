#!/usr/bin/env python3
"""
Modify each workload's etna-faultloc.rs to add a `--locate` mode that uses
`crabcheck::quickcheck_with_locate!` and emits a single-line JSON record on
stdout marked with `@@LOCATE@@`.

The existing `quickcheck(...)` dispatch stays as the default (back-compat).
When the binary is invoked with `--locate`, the same dispatch table is used
but each arm calls `quickcheck_with_locate!` with the workload's lib name
as the module argument.

The change is mechanical:
  1. Read package name from Cargo.toml. Compute module = name.replace("-", "_").
  2. Insert a `--locate`-handling block right before the existing main dispatch.
  3. Generate a parallel match by replacing `quickcheck(...)` with
     `crabcheck::profiling::quickcheck_with_locate(<closure>, "<module>")`
     and `quickcheck_with_shrink(<f>, <shrink>)` with the same (shrink is
     ignored for locate mode).
  4. Append a helper `emit_locate_json` to the file.

Idempotent: re-running on a file that already contains `@@LOCATE@@` is a no-op.
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKLOADS = ROOT / "workloads" / "Rust"

MARKER = "// crabcheck-quickcheck-with-locate-mode"

EMIT_HELPER = '''
// crabcheck-quickcheck-with-locate-mode
fn emit_locate_json(r: &crabcheck::profiling::LocateResult) {
    use crabcheck::quickcheck::ResultStatus;
    let status = match &r.run.status {
        ResultStatus::Failed { .. } => "Failed",
        ResultStatus::Finished => "Finished",
        ResultStatus::GaveUp => "GaveUp",
        ResultStatus::TimedOut => "TimedOut",
        ResultStatus::Aborted { .. } => "Aborted",
    };
    let top_json = if let Some(s) = r.top() {
        serde_json::json!({
            "rank": s.rank,
            "file": s.region.file,
            "function": s.region.function,
            "start_line": s.region.start_line,
            "end_line": s.region.end_line,
            "ochiai": s.region.suspiciousness.ochiai,
            "delta": s.region.delta,
            "panic_overlap": s.panic_overlap,
            "confidence": format!("{}", s.confidence),
            "confidence_rule": s.confidence_rule,
        })
    } else { serde_json::Value::Null };
    let top_5: Vec<_> = r.suspects.iter().take(5).map(|s| serde_json::json!({
        "rank": s.rank,
        "file": s.region.file,
        "function": s.region.function,
        "start_line": s.region.start_line,
        "end_line": s.region.end_line,
        "ochiai": s.region.suspiciousness.ochiai,
        "delta": s.region.delta,
        "panic_overlap": s.panic_overlap,
        "confidence": format!("{}", s.confidence),
        "confidence_rule": s.confidence_rule,
    })).collect();
    let diags: Vec<_> = r.diagnostics.iter().map(|d| d.tag()).collect();
    let out = serde_json::json!({
        "status": status,
        "passed": r.run.passed,
        "discarded": r.run.discarded,
        "n_panics": r.n_panics,
        "n_suspects": r.suspects.len(),
        "top": top_json,
        "top_5": top_5,
        "diagnostics": diags,
        "workdir": r.workdir.display().to_string(),
        "error": r.error,
    });
    println!("@@LOCATE@@ {}", out);
}
'''


def get_module(workload_dir: Path) -> str:
    cargo = (workload_dir / "Cargo.toml").read_text()
    m = re.search(r'^\s*name\s*=\s*"([^"]+)"', cargo, re.MULTILINE)
    if not m:
        raise SystemExit(f"no [package].name in {workload_dir}/Cargo.toml")
    return m.group(1).replace("-", "_")


def find_match_block(text: str):
    """Locate the `let result = match (...) { ... };` block.

    The match scrutinee may be `(tool, property)` or
    `(args[1].as_str(), args[2].as_str())` or similar. Accept any
    parenthesized 2-tuple.
    """
    pat = re.search(r'let result\s*=\s*match\s*\(', text)
    if not pat:
        return None
    let_start = pat.start()
    # Walk past the scrutinee parens.
    i = pat.end() - 1   # position of '(' that match's scrutinee opens with
    depth = 1
    j = i + 1
    while j < len(text) and depth > 0:
        c = text[j]
        if c == "(": depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0: break
        j += 1
    if depth != 0:
        return None
    # Skip whitespace, expect `{`
    k = j + 1
    while k < len(text) and text[k] in " \t\n\r":
        k += 1
    if k >= len(text) or text[k] != "{":
        return None
    open_idx = k
    depth = 1
    i = open_idx + 1
    while i < len(text) and depth > 0:
        if text[i] == "{": depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0: break
        i += 1
    # Find trailing `;`.
    semi = text.find(";", i)
    if semi == -1:
        return None
    return (let_start, semi + 1)


def parse_arms(match_block: str):
    """Extract (key_tuple, arm_body) for each `("...", "...") => ...` arm.

    Handles arms terminated by either an explicit `,` separator or a closing
    block-expression `}` (Rust allows omitting the comma after a `{ ... }`
    arm body). Returns list of (key_tuple_string, arm_body_string). Skips
    arms whose body is not a `quickcheck(...)` / `quickcheck_with_shrink(...)`
    call (i.e. wildcard / panic arms).
    """
    inner = re.search(r"\{(.*)\}\s*;\s*$", match_block, re.DOTALL).group(1)
    arms = []
    i = 0
    n = len(inner)
    while i < n:
        # Skip whitespace.
        while i < n and inner[i] in " \t\n\r":
            i += 1
        if i >= n:
            break
        # Capture the pattern (key tuple) — either `(... ...)`, `_`, or
        # something like `_ if cond`.
        key_start = i
        if inner[i] == "(":
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                c = inner[j]
                if c == "(": depth += 1
                elif c == ")": depth -= 1
                j += 1
                if depth == 0: break
            key_tuple = inner[key_start:j]
        else:
            # `_`, `_ if ...`, etc. — read until `=>`.
            j = inner.index("=>", i)
            key_tuple = inner[key_start:j].strip()
        # Skip whitespace then `=>`.
        k = j
        while k < n and inner[k] in " \t\n\r":
            k += 1
        if inner[k:k+2] != "=>":
            # Malformed; bail.
            break
        k += 2
        while k < n and inner[k] in " \t\n\r":
            k += 1
        # Body: walk until either (a) a top-level `,` or (b) we just closed
        # a top-level `{ ... }` block (Rust allows that to terminate the arm
        # without a comma).
        body_start = k
        depth_paren, depth_brace = 0, 0
        body_end = None
        while k < n:
            c = inner[k]
            if c == "(": depth_paren += 1
            elif c == ")": depth_paren -= 1
            elif c == "{": depth_brace += 1
            elif c == "}":
                depth_brace -= 1
                if depth_paren == 0 and depth_brace == 0:
                    body_end = k + 1
                    k += 1
                    break
            elif c == "," and depth_paren == 0 and depth_brace == 0:
                body_end = k
                break
            k += 1
        if body_end is None:
            body_end = k
        body = inner[body_start:body_end].strip()
        # Move past optional trailing comma + whitespace.
        while k < n and inner[k] in " \t\n\r":
            k += 1
        if k < n and inner[k] == ",":
            k += 1

        # Filter out wildcard / panic arms by peeking into the body.
        peek = body
        if peek.startswith("{") and peek.endswith("}"):
            peek = peek[1:-1].strip()
        if peek.startswith("quickcheck"):
            arms.append((key_tuple, body))
        i = k
    return arms


def rewrite_arm_body(body: str, module: str) -> str:
    """Rewrite a `quickcheck(closure)` or `quickcheck_with_shrink(f, shrink)`
    arm body into a `quickcheck_with_locate(closure, module)` call followed
    by a JSON emit.

    The body is the RHS of the match arm — typically:
      quickcheck(|i: T| {...})
      quickcheck_with_shrink(|i: T| {...}, shrink_fn)
      quickcheck(|i: T| to_opt(...))

    Returns Rust code that goes inside a `{ ... }` block in the new arm.
    """
    body = body.strip()
    if body.startswith("{") and body.endswith("}"):
        body = body[1:-1].strip()

    if body.startswith("quickcheck_with_shrink"):
        # Strip wrapping `quickcheck_with_shrink( ... )`
        inner = body[len("quickcheck_with_shrink"):].lstrip()
        assert inner.startswith("("), f"unexpected shape: {body[:80]}"
        # Find matching close paren of the outer call
        depth = 1
        j = 1
        while j < len(inner) and depth > 0:
            c = inner[j]
            if c == "(": depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0: break
            j += 1
        inside = inner[1:j].strip()
        # `inside` is `closure, shrink_fn` — split on top-level comma
        depth_paren, depth_brace = 0, 0
        comma = -1
        for k, c in enumerate(inside):
            if c == "(": depth_paren += 1
            elif c == ")": depth_paren -= 1
            elif c == "{": depth_brace += 1
            elif c == "}": depth_brace -= 1
            elif c == "," and depth_paren == 0 and depth_brace == 0:
                comma = k
                break
        closure = inside[:comma].strip() if comma != -1 else inside
        # Drop the shrinker for locate mode (no shrink-aware locate API yet).
        f_expr = closure
    elif body.startswith("quickcheck"):
        inner = body[len("quickcheck"):].lstrip()
        assert inner.startswith("("), f"unexpected shape: {body[:80]}"
        depth = 1
        j = 1
        while j < len(inner) and depth > 0:
            c = inner[j]
            if c == "(": depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0: break
            j += 1
        f_expr = inner[1:j].strip()
    else:
        raise SystemExit(f"don't know how to rewrite arm body: {body[:120]}")

    # Build the locate-mode arm body.
    # Note: we keep the closure as-is and pass it to the function form
    # (quickcheck_with_locate, not the macro) so we can supply the explicit
    # module string and avoid env! gotchas in binary contexts.
    return (
        "{\n"
        f"            let report = crabcheck::profiling::quickcheck_with_locate({f_expr}, \"{module}\");\n"
        "            emit_locate_json(&report);\n"
        "        }"
    )


def transform_file(path: Path) -> bool:
    text = path.read_text()
    if MARKER in text:
        return False
    workload_dir = path.parent.parent.parent.parent
    # arrayvec/src/bin/etna-faultloc.rs → workload_dir = .../arrayvec
    # but parents() of src/bin/etna-faultloc.rs = src/bin → src → workload_dir
    # so path.parent.parent.parent
    workload_dir = path.parent.parent.parent
    module = get_module(workload_dir)

    block = find_match_block(text)
    if not block:
        print(f"  SKIP {path.relative_to(ROOT)}: no match block found")
        return False
    let_start, let_end = block
    block_text = text[let_start:let_end]

    arms = parse_arms(block_text)
    if not arms:
        print(f"  SKIP {path.relative_to(ROOT)}: no arms parsed")
        return False

    # Build the locate-mode dispatch.
    locate_arms = []
    for key, body in arms:
        rewritten = rewrite_arm_body(body, module)
        locate_arms.append(f"        {key} => {rewritten},")
    locate_dispatch = "\n".join(locate_arms)

    locate_prelude = f'''    if std::env::args().any(|a| a == "--locate") {{
        match (tool, property) {{
{locate_dispatch}
            _ => panic!("Unknown: {{tool}} {{property}}"),
        }}
        return;
    }}
'''

    # Insert the locate prelude right before the existing `let result = match ...`
    new_text = text[:let_start] + locate_prelude + text[let_start:] + "\n" + EMIT_HELPER + "\n"
    path.write_text(new_text)
    return True


def main():
    files = list(WORKLOADS.glob("*/src/bin/etna-faultloc.rs")) + list(WORKLOADS.glob("*/*/src/bin/etna-faultloc.rs"))
    n = m = 0
    for f in sorted(files):
        n += 1
        if transform_file(f):
            print(f"  modified  {f.relative_to(ROOT)}")
            m += 1
        else:
            print(f"  skip      {f.relative_to(ROOT)}")
    print(f"\nfiles scanned={n} modified={m}")


if __name__ == "__main__":
    main()
