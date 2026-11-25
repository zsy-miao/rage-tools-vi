#!/usr/bin/env python3
"""Summarize class-0 bone centroids, extents, and shared-hash templates."""
import argparse
import csv
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("points", type=Path, nargs="?", default=Path("handoff/script-bone-points.tsv"))
    parser.add_argument("--tsv", type=Path, default=Path("handoff/script-bone-geometry.tsv"))
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()

    groups = defaultdict(lambda: {"root_class": "", "table": "", "hash": "", "points": [], "edges": 0, "zeros": 0})
    with args.points.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            key = (row["root_id"], row["table_record"], int(row["bone_index"]))
            group = groups[key]
            group["root_class"] = row["root_class"]
            group["table"] = row["table_record"]
            group["hash"] = row["bone_hash"]
            a = tuple(float(row[name]) for name in ("ax", "ay", "az"))
            b = tuple(float(row[name]) for name in ("bx", "by", "bz"))
            if row["kind"] == "zero":
                group["zeros"] += 1
            else:
                group["points"].append(a)
                if row["kind"] == "edge":
                    group["edges"] += 1
                    group["points"].append(b)

    def geometry(points):
        if not points:
            zero = (0.0, 0.0, 0.0)
            return zero, zero, zero
        centroid = tuple(sum(p[i] for p in points) / len(points) for i in range(3))
        low = tuple(min(p[i] for p in points) for i in range(3))
        high = tuple(max(p[i] for p in points) for i in range(3))
        return centroid, low, high

    by_root = defaultdict(list)
    for (root, table, index), group in groups.items():
        centroid, low, high = geometry(group["points"])
        by_root[root].append((index, centroid, low, high, group, table))

    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow([
            "root_id", "root_class", "table_record", "bone_index", "bone_hash",
            "points", "edges", "zeros", "cx", "cy", "cz",
            "min_x", "min_y", "min_z", "max_x", "max_y", "max_z",
            "extent_x", "extent_y", "extent_z",
        ])
        for root, bones in sorted(by_root.items()):
            for index, centroid, low, high, group, table in sorted(bones, key=lambda item: item[0]):
                extent = tuple(high[i] - low[i] for i in range(3))
                writer.writerow([
                    root, group["root_class"], table, index, group["hash"],
                    len(group["points"]), group["edges"], group["zeros"],
                    *(f"{v:.6g}" for v in centroid),
                    *(f"{v:.6g}" for v in low),
                    *(f"{v:.6g}" for v in high),
                    *(f"{v:.6g}" for v in extent),
                ])

    print(f"roots: {len(by_root)}; bones: {len(groups)}")
    print("root\tclass\tbones")
    for root, bones in sorted(by_root.items(), key=lambda item: -len(item[1]))[: args.limit]:
        print(f"{root}\t{bones[0][4]['root_class']}\t{len(bones)}")

    by_hash = defaultdict(list)
    for (root, table, index), group in groups.items():
        by_hash[group["hash"]].append((root, index, group))
    print("\ntop shared bone hashes")
    print("hash\troots\tbones\tavg_points\tavg_extent")
    for name_hash, entries in sorted(by_hash.items(), key=lambda item: -len({e[0] for e in item[1]}))[: args.limit]:
        roots = {e[0] for e in entries}
        avg_points = sum(len(e[2]["points"]) for e in entries) / len(entries)
        extents = []
        for root, index, group in entries:
            _, low, high = geometry(group["points"])
            extents.append(sum((high[i] - low[i]) for i in range(3)) / 3)
        print(f"{name_hash}\t{len(roots)}\t{len(entries)}\t{avg_points:.2f}\t{sum(extents)/len(extents):.5g}")


if __name__ == "__main__":
    main()
