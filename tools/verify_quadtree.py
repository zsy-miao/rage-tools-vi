#!/usr/bin/env python3
"""Verify the class-0 quadtree JSON against the geometry source."""
import argparse
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geometry", type=Path, default=Path("handoff/script-bone-geometry.tsv"))
    parser.add_argument("--json", type=Path, default=Path("output/script-quadtree/script-quadtree.json"))
    parser.add_argument("--out", type=Path, default=Path("handoff/script-quadtree-verification.tsv"))
    args = parser.parse_args()

    expected = {}
    flat = 0
    excluded = 0
    with args.geometry.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if int(row["points"]) == 0:
                excluded += 1
                continue
            rect = tuple(float(row[key]) for key in ("min_x", "min_y", "max_x", "max_y"))
            key = (row["root_id"], int(row["table_record"]), int(row["bone_index"]))
            expected[key] = rect
            flat += rect[0] == rect[2] or rect[1] == rect[3]

    trees = json.loads(args.json.read_text())
    seen = {}
    failures = []

    def walk(node, root_id):
        x0, y0, x1, y1 = node["bounds"]
        if x0 > x1 or y0 > y1:
            failures.append(f"bad node bounds {root_id} depth {node['depth']}")
        for item in node["items"]:
            ident = item["id"]
            key = (ident["root_id"], ident["table_record"], ident["bone_index"])
            if key in seen:
                failures.append(f"duplicate item {key}")
            seen[key] = item["rect"]
            ix0, iy0, ix1, iy1 = item["rect"]
            if not (x0 - 1e-9 <= ix0 <= ix1 <= x1 + 1e-9 and y0 - 1e-9 <= iy0 <= iy1 <= y1 + 1e-9):
                failures.append(f"item outside node {key}")
        for child in node["children"]:
            cx0, cy0, cx1, cy1 = child["bounds"]
            if not (x0 - 1e-9 <= cx0 <= cx1 <= x1 + 1e-9 and y0 - 1e-9 <= cy0 <= cy1 <= y1 + 1e-9):
                failures.append(f"child outside parent {root_id} depth {child['depth']}")
            walk(child, root_id)

    for root_id, tree in trees.items():
        walk(tree, root_id)

    missing = set(expected) - set(seen)
    extra = set(seen) - set(expected)
    if missing:
        failures.append(f"missing items: {len(missing)}")
    if extra:
        failures.append(f"extra items: {len(extra)}")

    rows = [
        ("roots", len(trees), "PASS" if len(trees) == 44 else "FAIL"),
        ("items", len(seen), "PASS" if len(seen) == len(expected) else "FAIL"),
        ("excluded_placeholders", excluded, "PASS" if excluded == 36 else "FAIL"),
        ("flat_extents", flat, "PASS" if flat == 412 else "FAIL"),
        ("duplicates", len(seen) - len(set(seen)), "PASS" if len(seen) == len(set(seen)) else "FAIL"),
        ("missing", len(missing), "PASS" if not missing else "FAIL"),
        ("extra", len(extra), "PASS" if not extra else "FAIL"),
        ("structural_failures", len(failures), "PASS" if not failures else "FAIL"),
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value", "status"])
        writer.writerows(rows)
    for row in rows:
        print(*row, sep="\t")
    if failures:
        for failure in failures[:20]:
            print(failure)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
