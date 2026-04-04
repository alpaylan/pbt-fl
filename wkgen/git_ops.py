import re
import subprocess

from . import output


def _run_git(repo, args):
    """Run a git command in the given repo directory."""
    result = subprocess.run(
        ["git", "-C", repo] + args,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git failed: {result.stderr.strip()}")
    return result.stdout


def _parse_diff(diff_text):
    """Parse unified diff text into structured file/hunk data."""
    files = []
    current_file = None
    current_hunk = None

    for line in diff_text.split("\n"):
        # New file in the diff
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.*) b/(.*)", line)
            path = m.group(2) if m else ""
            current_file = {"path": path, "status": "M", "hunks": []}
            files.append(current_file)
            current_hunk = None
            continue

        if current_file is None:
            continue

        # File header lines (before first hunk)
        if current_hunk is None:
            if line.startswith("new file"):
                current_file["status"] = "A"
            elif line.startswith("deleted file"):
                current_file["status"] = "D"
            elif line.startswith("rename from"):
                current_file["status"] = "R"

        # Hunk header
        if line.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)", line)
            if m:
                current_hunk = {
                    "header": line,
                    "old_start": int(m.group(1)),
                    "new_start": int(m.group(2)),
                    "content": line,
                }
                current_file["hunks"].append(current_hunk)
            continue

        # Hunk content lines
        if current_hunk is not None:
            current_hunk["content"] += "\n" + line

    return files


def batch(repo, offset=0, count=50):
    """Fetch a batch of commits with diffs."""
    # Get commit metadata
    raw = _run_git(
        repo,
        [
            "log",
            "--no-merges",
            f"--skip={offset}",
            f"-n{count}",
            "--format=%H\t%an <%ae>\t%aI\t%s",
        ],
    )

    if not raw.strip():
        output.ok([])
        return

    commits = []
    for line in raw.strip().split("\n"):
        parts = line.split("\t", 3)
        if len(parts) < 4:
            continue
        hash_, author, date, message = parts

        # Get diff for this commit
        try:
            diff_raw = _run_git(
                repo, ["diff-tree", "-p", "--root", "--no-commit-id", hash_]
            )
        except RuntimeError:
            diff_raw = ""

        files = _parse_diff(diff_raw)
        commits.append(
            {
                "hash": hash_,
                "message": message,
                "author": author,
                "date": date,
                "files": files,
            }
        )

    output.ok(commits)


def show(repo, commit):
    """Full details of one commit."""
    # Get metadata
    raw = _run_git(
        repo,
        ["show", "--format=%H\t%an <%ae>\t%aI\t%B", "--no-patch", commit],
    )
    parts = raw.strip().split("\t", 3)
    if len(parts) < 4:
        raise RuntimeError(f"unexpected git show output for {commit}")

    hash_, author, date, body = parts

    # Get diff
    try:
        diff_raw = _run_git(
            repo, ["diff-tree", "-p", "--root", "--no-commit-id", commit]
        )
    except RuntimeError:
        diff_raw = ""

    files = _parse_diff(diff_raw)
    output.ok(
        {
            "hash": hash_,
            "message": body.strip(),
            "author": author,
            "date": date,
            "files": files,
        }
    )


def diff_range(repo, from_hash, to_hash):
    """Composed diff between two commits."""
    diff_raw = _run_git(repo, ["diff", f"{from_hash}..{to_hash}"])
    files = _parse_diff(diff_raw)
    output.ok(
        {
            "from": from_hash,
            "to": to_hash,
            "files": files,
        }
    )
