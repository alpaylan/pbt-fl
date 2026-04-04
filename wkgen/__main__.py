import argparse
import sys

from . import output


def main():
    parser = argparse.ArgumentParser(
        prog="wkgen",
        description="Workload generation scaffolding tool",
    )
    subparsers = parser.add_subparsers(dest="group")

    # --- git ---
    git_parser = subparsers.add_parser("git", help="Git history operations")
    git_subs = git_parser.add_subparsers(dest="action")

    git_batch = git_subs.add_parser("batch", help="Fetch batch of commits with diffs")
    git_batch.add_argument("--repo", required=True, help="Path to git repo")
    git_batch.add_argument("--offset", type=int, default=0, help="Skip N commits")
    git_batch.add_argument("--count", type=int, default=50, help="Number of commits")

    git_show = git_subs.add_parser("show", help="Full details of one commit")
    git_show.add_argument("--repo", required=True, help="Path to git repo")
    git_show.add_argument("--commit", required=True, help="Commit hash")

    git_diff = git_subs.add_parser("diff-range", help="Composed diff between two commits")
    git_diff.add_argument("--repo", required=True, help="Path to git repo")
    git_diff.add_argument("--from", dest="from_hash", required=True, help="Start commit")
    git_diff.add_argument("--to", dest="to_hash", required=True, help="End commit")

    # --- marauders ---
    mar_parser = subparsers.add_parser("marauders", help="Marauders mutation operations")
    mar_subs = mar_parser.add_subparsers(dest="action")

    mar_list = mar_subs.add_parser("list", help="List all mutations in a project")
    mar_list.add_argument("--path", required=True, help="Project directory")

    mar_convert = mar_subs.add_parser("convert", help="Convert mutation syntax")
    mar_convert.add_argument("--path", required=True, help="File path")
    mar_convert.add_argument(
        "--to",
        required=True,
        choices=["functional", "comment"],
        help="Target syntax",
    )

    # --- test ---
    test_parser = subparsers.add_parser("test", help="Test execution")
    test_subs = test_parser.add_subparsers(dest="action")

    test_variant = test_subs.add_parser("variant", help="Run tests with variant active")
    test_variant.add_argument("--workload-dir", required=True, help="Workload directory")
    test_variant.add_argument("--variant", required=True, help="Variant name")
    test_variant.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")
    test_variant.add_argument("--test-filter", help="Filter tests by name")

    test_base = test_subs.add_parser("base", help="Run tests with no variant (base case)")
    test_base.add_argument("--workload-dir", required=True, help="Workload directory")
    test_base.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")

    # --- checkpoint ---
    cp_parser = subparsers.add_parser("checkpoint", help="Checkpoint management")
    cp_subs = cp_parser.add_subparsers(dest="action")

    cp_write = cp_subs.add_parser("write", help="Write JSON checkpoint")
    cp_write.add_argument("--project-dir", required=True, help="Project directory")
    cp_write.add_argument("--stage", required=True, help="Checkpoint stage name")
    cp_write.add_argument(
        "--data-stdin",
        action="store_true",
        default=True,
        help="Read data from stdin (default)",
    )

    cp_read = cp_subs.add_parser("read", help="Read a checkpoint")
    cp_read.add_argument("--project-dir", required=True, help="Project directory")
    cp_read.add_argument("--stage", required=True, help="Checkpoint stage name")

    cp_list = cp_subs.add_parser("list", help="List available checkpoints")
    cp_list.add_argument("--project-dir", required=True, help="Project directory")

    # --- init ---
    init_parser = subparsers.add_parser("init", help="Set up working directory for a new project")
    init_parser.add_argument("--repo", required=True, help="Git repo URL or local path")
    init_parser.add_argument("--name", required=True, help="Project name")

    # --- agent ---
    agent_parser = subparsers.add_parser("agent", help="Run workload-generation agent orchestration")
    agent_subs = agent_parser.add_subparsers(dest="action")

    agent_run = agent_subs.add_parser("run", help="Run staged agent pipeline")
    agent_run.add_argument("--project-dir", required=True, help="Workload project directory")
    agent_run.add_argument(
        "--backend",
        default="dry",
        choices=["dry", "pi"],
        help="Backend for stage generation",
    )
    agent_run.add_argument(
        "--no-resume",
        action="store_true",
        help="Start a new run_id instead of resuming existing agent_state",
    )
    agent_run.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing stage checkpoint files",
    )
    agent_run.add_argument(
        "--from-stage",
        choices=[
            "candidates",
            "ranked",
            "fixes",
            "classified",
            "tests",
            "mutations",
            "report",
            "docs",
            "validation",
        ],
        help="First stage to run",
    )
    agent_run.add_argument(
        "--to-stage",
        choices=[
            "candidates",
            "ranked",
            "fixes",
            "classified",
            "tests",
            "mutations",
            "report",
            "docs",
            "validation",
        ],
        help="Last stage to run",
    )
    agent_run.add_argument(
        "--pi-cmd",
        default="pi run --json --stage {stage}",
        help="Command template for pi backend. Placeholders: {stage}, {project_dir}",
    )

    agent_status = agent_subs.add_parser("status", help="Show agent run/checkpoint status")
    agent_status.add_argument("--project-dir", required=True, help="Workload project directory")

    # --- parse and dispatch ---
    args = parser.parse_args()

    if not args.group:
        parser.print_help()
        sys.exit(1)

    try:
        _dispatch(args)
    except Exception as e:
        output.err(str(e))
        sys.exit(1)


def _dispatch(args):
    group = args.group
    action = getattr(args, "action", None)

    if group == "git":
        from . import git_ops

        if action == "batch":
            git_ops.batch(args.repo, args.offset, args.count)
        elif action == "show":
            git_ops.show(args.repo, args.commit)
        elif action == "diff-range":
            git_ops.diff_range(args.repo, args.from_hash, args.to_hash)
        else:
            raise RuntimeError("missing action: batch | show | diff-range")

    elif group == "marauders":
        from . import marauders_ops

        if action == "list":
            marauders_ops.list_mutations(args.path)
        elif action == "convert":
            marauders_ops.convert(args.path, args.to)
        else:
            raise RuntimeError("missing action: list | convert")

    elif group == "test":
        from . import test_ops

        if action == "variant":
            test_ops.variant(
                args.workload_dir, args.variant, args.timeout, args.test_filter
            )
        elif action == "base":
            test_ops.base(args.workload_dir, args.timeout)
        else:
            raise RuntimeError("missing action: variant | base")

    elif group == "checkpoint":
        from . import checkpoint_ops

        if action == "write":
            checkpoint_ops.write(args.project_dir, args.stage)
        elif action == "read":
            checkpoint_ops.read(args.project_dir, args.stage)
        elif action == "list":
            checkpoint_ops.list_checkpoints(args.project_dir)
        else:
            raise RuntimeError("missing action: write | read | list")

    elif group == "init":
        from . import init_ops

        init_ops.init(args.repo, args.name)

    elif group == "agent":
        from . import agent_ops

        if action == "run":
            agent_ops.run(
                project_dir=args.project_dir,
                backend=args.backend,
                resume=not args.no_resume,
                force=args.force,
                from_stage=args.from_stage,
                to_stage=args.to_stage,
                pi_cmd=args.pi_cmd,
            )
        elif action == "status":
            agent_ops.status(args.project_dir)
        else:
            raise RuntimeError("missing action: run | status")

    else:
        raise RuntimeError(f"unknown group: {group}")


if __name__ == "__main__":
    main()
