#!/usr/bin/env python3
"""
One-shot migration: remove the workload-side `safe_call` panic-capturing
wrapper now that crabcheck::profiling owns that responsibility.

For every workloads/Rust/<name>/src/bin/etna-faultloc.rs:
  1. Delete the 28-line `fn safe_call<F: ...>` block (byte-identical across
     33 files; MD5 26b709f0e8a93a87569d6a68305cb067).
  2. Rewrite each `safe_call(|| EXPR)` call as `EXPR`. EXPR may contain nested
     parens, so we use a balanced-paren scan rather than a regex.

Files without the safe_call block (aho-corasick, crc32fast) are untouched.
The 3 tree-style workloads (BST, RBT, STLC) live elsewhere and are also
unaffected.

Idempotent: re-running on a cleaned file is a no-op (no `safe_call` strings
left to find).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN_GLOB = ROOT / "workloads" / "Rust"

OLD_SAFE_CALL = '''fn safe_call<F: FnOnce() -> Option<bool> + std::panic::UnwindSafe>(f: F) -> Option<bool> {
    use std::backtrace::Backtrace;
    use std::sync::{Arc, Mutex};
    let captured: Arc<Mutex<Option<(String, u32, String)>>> = Arc::new(Mutex::new(None));
    let cap = Arc::clone(&captured);
    let prev = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let bt = Backtrace::force_capture().to_string();
        let (file, line) = info.location()
            .map(|l| (l.file().to_string(), l.line()))
            .unwrap_or_default();
        *cap.lock().unwrap() = Some((file, line, bt));
    }));
    let result = std::panic::catch_unwind(f).unwrap_or(Some(false));
    std::panic::set_hook(prev);
    if let Some((file, line, bt)) = captured.lock().unwrap().take() {
        if !file.is_empty() {
            use std::io::Write;
            let esc = |s: &str| s.replace('\\\\', r"\\\\").replace('"', r#"\\""#)
                .replace('\\n', r"\\n").replace('\\r', r"\\r").replace('\\t', r"\\t");
            if let Ok(mut f) = std::fs::OpenOptions::new()
                .create(true).append(true).open("coverage/panic_locations.jsonl") {
                let _ = writeln!(f, r#"{{{{"file":"{{}}","line":{{}},"bt":"{{}}"}}}}"#, esc(&file), line, esc(&bt));
            }
        }
    }
    result
}
'''
# NB: the literal block in the source files is escaped Rust, so the Python
# string above contains the actual file bytes. We don't construct it from
# parts — we read one known file and use that as the deletion needle, to
# avoid escaping mistakes.

CANONICAL_FILE = BIN_GLOB / "bytes" / "src" / "bin" / "etna-faultloc.rs"

def load_safe_call_block(path: Path) -> str:
    """Return the exact byte range that contains the safe_call function."""
    text = path.read_text()
    m = re.search(r"fn safe_call<F: FnOnce\(\) -> Option<bool>", text)
    if not m:
        raise SystemExit(f"safe_call not found in canonical file {path}")
    start = m.start()
    # Find matching close brace at top level. Walk forward counting braces.
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                # Include the closing brace and any trailing newline.
                end = i + 1
                if end < len(text) and text[end] == "\n":
                    end += 1
                return text[start:end]
        i += 1
    raise SystemExit("safe_call braces unbalanced in canonical file")

def strip_calls(text: str) -> str:
    """Replace every safe_call(|| EXPR) with EXPR. EXPR may contain ()."""
    NEEDLE = "safe_call(|| "
    out = []
    i = 0
    while True:
        idx = text.find(NEEDLE, i)
        if idx == -1:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:idx])
        # Position just after the `(` we just consumed via NEEDLE.
        start = idx + len(NEEDLE)
        depth = 1
        j = start
        while j < len(text) and depth > 0:
            c = text[j]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= len(text):
            raise SystemExit(f"unbalanced safe_call(|| starting at offset {idx}")
        out.append(text[start:j])
        i = j + 1  # skip the matching `)`

def main():
    block = load_safe_call_block(CANONICAL_FILE)
    n_files = n_changed = n_calls_removed = 0
    for f in sorted(BIN_GLOB.glob("*/src/bin/etna-faultloc.rs")):
        n_files += 1
        text = f.read_text()
        original = text
        had_block = block in text
        had_calls = "safe_call(|| " in text
        if had_block:
            text = text.replace(block, "")
        if had_calls:
            calls_before = text.count("safe_call(|| ")
            text = strip_calls(text)
            n_calls_removed += calls_before
        if text != original:
            f.write_text(text)
            n_changed += 1
            print(f"  modified  {f.relative_to(ROOT)}")
        else:
            tag = "skip(clean)" if not had_block and not had_calls else "skip(other)"
            print(f"  {tag:<11} {f.relative_to(ROOT)}")
    print(f"\nfiles scanned={n_files} modified={n_changed} call-sites stripped={n_calls_removed}")

if __name__ == "__main__":
    main()
