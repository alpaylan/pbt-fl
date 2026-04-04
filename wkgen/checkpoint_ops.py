import json
import os
import sys
import tempfile

from . import output


def _checkpoints_dir(project_dir):
    return os.path.join(project_dir, "checkpoints")


def write(project_dir, stage):
    """Write a JSON checkpoint atomically (reads data from stdin)."""
    checkpoints = _checkpoints_dir(project_dir)
    os.makedirs(checkpoints, exist_ok=True)

    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"invalid JSON on stdin: {e}")

    target = os.path.join(checkpoints, f"{stage}.json")

    # Atomic write: write to temp file then rename
    fd, tmp_path = tempfile.mkstemp(
        dir=checkpoints, prefix=f".{stage}_", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, target)
    except BaseException:
        # Clean up temp file on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    output.ok({"stage": stage, "path": target})


def read(project_dir, stage):
    """Read a checkpoint."""
    target = os.path.join(_checkpoints_dir(project_dir), f"{stage}.json")
    if not os.path.exists(target):
        raise RuntimeError(f"checkpoint not found: {stage}")

    with open(target) as f:
        data = json.load(f)

    output.ok({"stage": stage, "data": data})


def list_checkpoints(project_dir):
    """List available checkpoints."""
    checkpoints = _checkpoints_dir(project_dir)
    if not os.path.isdir(checkpoints):
        output.ok([])
        return

    stages = []
    for name in sorted(os.listdir(checkpoints)):
        if name.endswith(".json") and not name.startswith("."):
            stages.append(name[: -len(".json")])

    output.ok(stages)
