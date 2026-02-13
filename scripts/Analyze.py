if __name__ == "__main__":
    import os
    import pathlib
    import json
    import argparse
    from statistics import mean, median

    parser = argparse.ArgumentParser(description="Analyze fault localization results")
    parser.add_argument(
        "--sort-by",
        choices=["tarantula", "ochiai", "dstar", "jaccard", "op2", "delta"],
        default="ochiai",
        help="Suspiciousness metric to sort regions by (default: ochiai)",
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Evaluate fault localization metrics against ground truth",
    )
    parser.add_argument(
        "--workload",
        choices=["BST", "RBT", "STLC"],
        help="Filter to a specific workload (only used with --evaluate)",
    )
    args = parser.parse_args()

    # Ground truth: (workload, mutation) -> (line_start, line_end) in implementation.rs
    GROUND_TRUTH = {
        # BST
        ("BST", "insert_1"): (27, 64),
        ("BST", "insert_2"): (27, 64),
        ("BST", "insert_3"): (27, 64),
        ("BST", "delete_4"): (78, 114),
        ("BST", "delete_5"): (78, 114),
        ("BST", "union_6"): (145, 215),
        ("BST", "union_7"): (145, 215),
        ("BST", "union_8"): (145, 215),
        # RBT
        ("RBT", "insert_1"): (138, 206),
        ("RBT", "insert_2"): (138, 206),
        ("RBT", "insert_3"): (138, 206),
        ("RBT", "miscolor_insert"): (138, 206),
        ("RBT", "no_balance_insert_1"): (138, 206),
        ("RBT", "no_balance_insert_2"): (138, 206),
        ("RBT", "swap_cd"): (80, 136),
        ("RBT", "swap_bc"): (80, 136),
        ("RBT", "miscolor_balLeft"): (208, 238),
        ("RBT", "miscolor_balRight"): (240, 270),
        ("RBT", "miscolor_join_1"): (272, 339),
        ("RBT", "miscolor_join_2"): (272, 339),
        ("RBT", "delete_4"): (345, 388),
        ("RBT", "delete_5"): (345, 388),
        ("RBT", "miscolor_delete"): (428, 437),
        # STLC
        ("STLC", "shift_var_none"): (88, 124),
        ("STLC", "shift_var_all"): (88, 124),
        ("STLC", "shift_var_leq"): (88, 124),
        ("STLC", "shift_abs_no_incr"): (88, 124),
        ("STLC", "subst_var_all"): (126, 157),
        ("STLC", "subst_var_none"): (126, 157),
        ("STLC", "subst_abs_no_shift"): (126, 157),
        ("STLC", "subst_abs_no_incr"): (126, 157),
        ("STLC", "substTop_no_shift"): (159, 171),
        ("STLC", "substTop_no_shift_back"): (159, 171),
    }

    METRICS = ["tarantula", "ochiai", "dstar", "jaccard", "op2"]

    def overlaps(region_start, region_end, truth_start, truth_end):
        """Check if a region overlaps with the ground truth range."""
        return region_start <= truth_end and region_end >= truth_start

    def find_fault_rank(impl_regions, metric, truth_start, truth_end):
        """
        Sort regions by metric descending, find rank of first region overlapping
        ground truth. Uses best-rank tie-breaking: all regions with the same score
        share the rank of the first in that group.

        Returns (rank, total) or (None, total) if not found.
        """
        sorted_regions = sorted(
            impl_regions,
            key=lambda r: r.get("suspiciousness", {}).get(metric, 0),
            reverse=True,
        )
        total = len(sorted_regions)

        # Assign best-rank (tied scores get the same rank)
        current_rank = 1
        prev_score = None
        for i, region in enumerate(sorted_regions):
            score = region.get("suspiciousness", {}).get(metric, 0)
            if score != prev_score:
                current_rank = i + 1
                prev_score = score
            if overlaps(
                region["start_line"], region["end_line"], truth_start, truth_end
            ):
                return (current_rank, total)

        return (None, total)

    if args.evaluate:
        # Read all entries
        with open(pathlib.Path(os.getcwd(), "store.jsonl"), "r") as f:
            lines = f.readlines()

        entries = []
        for line in lines:
            result = json.loads(line)["data"]
            workload = result.get("workload", "")
            if args.workload and workload != args.workload:
                continue
            mutations = result.get("mutations", [])
            if not mutations:
                continue
            mutation = mutations[0]
            prop = result.get("property", "")
            regions = result.get("regions", [])

            # Filter to implementation.rs regions with suspiciousness
            impl_regions = [
                r
                for r in regions
                if r.get("file", "").endswith("implementation.rs")
                and r.get("suspiciousness")
            ]
            if not impl_regions:
                continue

            truth_key = (workload, mutation)
            if truth_key not in GROUND_TRUTH:
                continue

            truth_start, truth_end = GROUND_TRUTH[truth_key]

            ranks = {}
            total = None
            for metric in METRICS:
                rank, total = find_fault_rank(
                    impl_regions, metric, truth_start, truth_end
                )
                ranks[metric] = rank

            entries.append(
                {
                    "workload": workload,
                    "mutation": mutation,
                    "property": prop,
                    "ranks": ranks,
                    "total": total,
                }
            )

        if not entries:
            print("No matching entries with suspiciousness data found.")
            exit(0)

        # Per-entry table
        print("\n=== Per-Entry Fault Localization Rankings ===")
        header = (
            f" {'Mutation':<30} {'Property':<20}"
            f" | {'tarantula':>10} | {'ochiai':>10} | {'dstar':>10}"
            f" | {'jaccard':>10} | {'op2':>10}"
        )
        print(header)
        print(" " + "-" * (len(header) - 1))

        for e in entries:
            cols = []
            for metric in METRICS:
                r = e["ranks"][metric]
                if r is not None:
                    cols.append(f"{r}/{e['total']}")
                else:
                    cols.append("N/A")
            print(
                f" {e['mutation']:<30} {e['property']:<20}"
                f" | {cols[0]:>10} | {cols[1]:>10} | {cols[2]:>10}"
                f" | {cols[3]:>10} | {cols[4]:>10}"
            )

        # Summary statistics per metric
        print("\n=== Summary Statistics ===")
        summary_header = (
            f" {'Metric':<12}"
            f" | {'Avg Rank':>10} | {'Med Rank':>10} | {'EXAM %':>8}"
            f" | {'Top-1':>6} | {'Top-3':>6} | {'Top-5':>6} | {'Top-10':>6}"
        )
        print(summary_header)
        print(" " + "-" * (len(summary_header) - 1))

        for metric in METRICS:
            valid = [e for e in entries if e["ranks"][metric] is not None]
            if not valid:
                print(f" {metric:<12} | {'No data':>10}")
                continue

            ranks_list = [e["ranks"][metric] for e in valid]
            totals = [e["total"] for e in valid]
            avg_rank = mean(ranks_list)
            med_rank = median(ranks_list)
            exam_scores = [(r - 1) / t * 100 for r, t in zip(ranks_list, totals)]
            avg_exam = mean(exam_scores)

            n = len(valid)
            top1 = sum(1 for r in ranks_list if r <= 1) / n * 100
            top3 = sum(1 for r in ranks_list if r <= 3) / n * 100
            top5 = sum(1 for r in ranks_list if r <= 5) / n * 100
            top10 = sum(1 for r in ranks_list if r <= 10) / n * 100

            print(
                f" {metric:<12}"
                f" | {avg_rank:>10.2f} | {med_rank:>10.1f} | {avg_exam:>7.2f}%"
                f" | {top1:>5.1f}% | {top3:>5.1f}% | {top5:>5.1f}% | {top10:>5.1f}%"
            )

        print(f"\nTotal entries evaluated: {len(entries)}")

    else:
        # Existing display mode
        with open(pathlib.Path(os.getcwd(), "store.jsonl"), "r") as f:
            lines = f.readlines()
            for line in lines:
                result = json.loads(line)["data"]
                regions = result.get("regions", [])

                # Sort by chosen metric descending
                def sort_key(region):
                    susp = region.get("suspiciousness")
                    if susp and args.sort_by != "delta":
                        return susp.get(args.sort_by, 0)
                    return region.get("delta", 0)

                sorted_regions = sorted(regions, key=sort_key, reverse=True)

                # Filter to positive deltas for display (backward-compatible)
                positive_regions = [
                    r for r in sorted_regions if r.get("delta", 0) > 0.01
                ]

                print(
                    f"\nMutations {result.get('mutations', [])}, Property: {result.get('property', '')}"
                )

                has_susp = any(r.get("suspiciousness") for r in positive_regions)
                if has_susp:
                    header = (
                        f" {'Region':<40} | {'Pos':>5} {'Neg':>5} {'Δ':>5}"
                        f" | {'Taran':>6} {'Ochiai':>6} {'DStar':>8} {'Jaccard':>7} {'Op2':>7}"
                    )
                    print(header)
                    print(" " + "-" * (len(header) - 1))

                for region in positive_regions:
                    file = pathlib.Path(region.get("file", "")).name
                    file_line_col = f"{file}:{region['start_line']}:{region['start_col']} - {region['end_line']}:{region['end_col']}"
                    base = (
                        f" {file_line_col:<40}"
                        f" | +{round(region['positive_avg'], 2):<5}"
                        f" -{round(region['negative_avg'], 2):<5}"
                        f" Δ{round(region['delta'], 2):<5}"
                    )
                    susp = region.get("suspiciousness")
                    if susp:
                        base += (
                            f" | {susp.get('tarantula', 0):>6.4f}"
                            f" {susp.get('ochiai', 0):>6.4f}"
                            f" {susp.get('dstar', 0):>8.2f}"
                            f" {susp.get('jaccard', 0):>7.4f}"
                            f" {susp.get('op2', 0):>7.2f}"
                        )
                    print(base)

        print(f"Total trials: {len(lines)}")
