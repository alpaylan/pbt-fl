if __name__ == "__main__":
    import os
    import pathlib
    import json
    import argparse

    parser = argparse.ArgumentParser(description="Analyze fault localization results")
    parser.add_argument(
        "--sort-by",
        choices=["tarantula", "ochiai", "dstar", "jaccard", "op2", "delta"],
        default="ochiai",
        help="Suspiciousness metric to sort regions by (default: ochiai)",
    )
    args = parser.parse_args()

    # Read `store.jsonl`
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
            positive_regions = [r for r in sorted_regions if r.get("delta", 0) > 0.01]

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
