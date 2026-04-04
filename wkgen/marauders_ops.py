import re
import subprocess

from . import output


def _run_marauders(args, cwd=None):
    """Run a marauders command."""
    result = subprocess.run(
        ["marauders"] + args,
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    if result.returncode != 0:
        raise RuntimeError(f"marauders failed: {result.stderr.strip()}")
    return result.stdout


def _parse_list_output(raw):
    """Parse marauders list output into structured data.

    Example line:
    ./src/implementation.rs:31 (name: insert, active: base, variants: ["insert_1", "insert_2"], tags: [])
    """
    mutations = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(
            r"(.+?):(\d+) \(name: (.+?), active: (.+?), "
            r'variants: \[(.+?)\], tags: \[(.*?)\]\)',
            line,
        )
        if not m:
            continue

        variants_str = m.group(5)
        tags_str = m.group(6)

        variants = [v.strip().strip('"') for v in variants_str.split(",")]
        tags = (
            [t.strip().strip('"') for t in tags_str.split(",") if t.strip()]
            if tags_str.strip()
            else []
        )

        mutations.append(
            {
                "file": m.group(1),
                "line": int(m.group(2)),
                "name": m.group(3),
                "active": m.group(4),
                "variants": variants,
                "tags": tags,
            }
        )
    return mutations


def list_mutations(path):
    """List all mutations in a project."""
    raw = _run_marauders(["list", "--path", path], cwd=path)
    mutations = _parse_list_output(raw)
    output.ok(mutations)


def convert(path, to_format):
    """Convert mutation syntax in a file."""
    _run_marauders(["convert", "--path", path, "--to", to_format])
    output.ok({"path": path, "format": to_format})
