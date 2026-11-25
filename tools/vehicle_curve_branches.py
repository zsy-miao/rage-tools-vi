#!/usr/bin/env python3
"""Compare branch samples for known window channels and unknown mover channels."""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

WINDOWS = {
    "0x86d36840": "window_lf_mover",
    "0x031fd5fc": "window_rf_mover",
    "0x6ec686bf": "window_lr_mover",
    "0xfc0ce3f6": "window_rr_mover",
}
UNKNOWN = ("0xfbdba1a6", "0x8bb5d91e", "0xeaeecb7b", "0x0552ea55")
ROOTS = ("astron", "216cstreamer", "airbus")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("points", type=Path, nargs="?", default=Path("handoff/script-vehicle-curve-points.tsv"))
    parser.add_argument("--tsv", type=Path, default=Path("handoff/script-vehicle-branch-relations.tsv"))
    args = parser.parse_args()

    data = defaultdict(list)
    with args.points.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["root_name"] not in ROOTS:
                continue
            key = (row["root_name"], row["key_hash"], row["array_record"])
            data[key].append(row)

    rows = []
    for (root, key, record), points in sorted(data.items()):
        points.sort(key=lambda item: int(item["point_index"]))
        samples = [(float(p["t"]), float(p["y"]), float(p["z"])) for p in points]
        end = samples[-1]
        rows.append((root, key, record, len(samples), end[0], end[1], end[2]))

    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["root_name", "key_hash", "key_name", "array_record", "points", "t_end", "y_end", "z_end"])
        for root, key, record, points, t, y, z in rows:
            writer.writerow([root, key, WINDOWS.get(key, ""), record, points, f"{t:.6g}", f"{y:.6g}", f"{z:.6g}"])

    for root in ROOTS:
        print(f"=== {root} ===")
        for key in list(WINDOWS) + list(UNKNOWN):
            group = [row for row in rows if row[0] == root and row[1] == key]
            if not group:
                continue
            print(f"{key} {WINDOWS.get(key, '-')}")
            for _, _, record, points, t, y, z in group:
                print(f"  rec={record} points={points} end=({t:.3f},{y:.4f},{z:.4f})")
        print()


if __name__ == "__main__":
    main()
