import os
import subprocess
import time

from . import MAX_OUTPUT_SIZE, output


def _truncate(text):
    if len(text) > MAX_OUTPUT_SIZE:
        return text[:MAX_OUTPUT_SIZE] + f"\n... (truncated, {len(text)} bytes total)"
    return text


def _run_cargo_test(workload_dir, env, timeout, test_filter=None):
    """Run cargo test and return structured result."""
    cmd = ["cargo", "test"]
    if test_filter:
        cmd.append(test_filter)

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            cwd=workload_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as e:
        exit_code = -1
        stdout = (e.stdout or b"").decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = (e.stderr or b"").decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
    elapsed = time.monotonic() - start

    return {
        "passed": exit_code == 0,
        "exit_code": exit_code,
        "stdout": _truncate(stdout),
        "stderr": _truncate(stderr),
        "duration_seconds": round(elapsed, 2),
    }


def _clean_env():
    """Return a copy of the environment with all M_* variables removed."""
    return {k: v for k, v in os.environ.items() if not k.startswith("M_")}


def variant(workload_dir, variant_name, timeout=60, test_filter=None):
    """Run tests with a specific variant active."""
    env = _clean_env()
    env[f"M_{variant_name}"] = "active"

    result = _run_cargo_test(workload_dir, env, timeout, test_filter)
    result["variant"] = variant_name
    output.ok(result)


def base(workload_dir, timeout=60):
    """Run tests with no variant (base case)."""
    env = _clean_env()

    result = _run_cargo_test(workload_dir, env, timeout)
    result["variant"] = None
    output.ok(result)
