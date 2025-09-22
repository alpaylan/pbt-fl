if __name__ == "__main__":
    import os
    import pathlib
    import json

    # Read `store.jsonl`
    with open(pathlib.Path(os.getcwd(), "store.jsonl"), "r") as f:
        lines = f.readlines()
        for line in lines:
            result = json.loads(line)["data"]
            # For each result, count how many regions have positive deltas
            positive_deltas = list(
                filter(
                    lambda region: region.get("delta", 0) > 0.01,
                    result.get("regions", []),
                )
            )
            print(
                f"\nMutations {result.get('mutations', [])}, Property: {result.get('property', '')}"
            )
            for region in positive_deltas:
                # Print the file name, start line:col, end line:col, and positive, negative, delta
                file = pathlib.Path(region.get("file", "")).name
                file_line_col = f"{file}:{region['start_line']}:{region['start_col']} - {region['end_line']}:{region['end_col']}"
                print(
                    f" {file_line_col:<40} | +{round(region['positive_avg'], 2):<5} -{round(region['negative_avg'], 2):<5} Δ{round(region['delta'], 2):<5}"
                )

    print(f"Total trials: {len(lines)}")
