import json
import os
import subprocess

from . import output


def init(repo, name):
    """Set up working directory for a new project."""
    project_dir = os.path.abspath(name)

    if os.path.exists(project_dir):
        raise RuntimeError(f"directory already exists: {project_dir}")

    # Determine if repo is a URL or local path
    is_url = repo.startswith("http://") or repo.startswith("https://") or repo.startswith("git@")

    if is_url:
        # Clone the repo
        repo_dir = os.path.join(project_dir, "repo")
        result = subprocess.run(
            ["git", "clone", repo, repo_dir],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git clone failed: {result.stderr.strip()}")
        repo_path = repo_dir
    else:
        # Validate local repo
        repo_path = os.path.abspath(repo)
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            raise RuntimeError(f"not a git repository: {repo_path}")

    # Create project directories
    os.makedirs(project_dir, exist_ok=True)
    os.makedirs(os.path.join(project_dir, "checkpoints"), exist_ok=True)

    # Write config
    config = {
        "name": name,
        "repo": repo_path,
        "language": "Rust",
    }
    config_path = os.path.join(project_dir, "wkgen.json")
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    output.ok(
        {
            "project_dir": project_dir,
            "repo": repo_path,
            "config": config_path,
        }
    )
