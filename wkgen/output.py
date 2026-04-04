import json
import sys


def ok(data):
    """Print success envelope to stdout."""
    json.dump({"ok": True, "data": data}, sys.stdout)
    sys.stdout.write("\n")


def err(message):
    """Print error envelope to stdout."""
    json.dump({"ok": False, "error": str(message)}, sys.stdout)
    sys.stdout.write("\n")


def log(message):
    """Log a message to stderr."""
    print(f"[wkgen] {message}", file=sys.stderr)
