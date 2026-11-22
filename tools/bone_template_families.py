#!/usr/bin/env python3
"""Cluster class-0 roots into near-identical bone-template families."""
import argparse
import csv
from collections import defaultdict
from pathlib import Path


class UnionFind:
    def __init__(self, items):
        self.parent = {item: item for item in items}

    def find(self, item):
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left, right):
        a, b = self.find(left), self.find(right)
        if a != b:
            self.parent[b] = a


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bones", type=Path, nargs="?", default=Path("handoff/script-bones.tsv"))
    parser.add_argument("--tsv", type=Path, default=Path("handoff/script-bone-template-families.tsv"))
    parser.add_argument("--jaccard", type=float, default=0.75)
    parser.add_argument("--geometry", type=Path, default=Path("handoff/script-bone-geometry.tsv"))
    args = parser.parse_args()

    roots = defaultdict(set)
    with args.bones.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            roots[row["root_id"]].add(row["bone_hash"])

    boxes = defaultdict(lambda: [1e9, 1e9, 1e9, -1e9, -1e9, -1e9])
    if args.geometry.is_file():
        with args.geometry.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                root = row["root_id"]
                for i, key in enumerate(("min_x", "min_y", "min_z", "max_x", "max_y", "max_z")):
                    value = float(row[key])
                    boxes[root][i] = min(boxes[root][i], value) if i < 3 else max(boxes[root][i], value)

    items = list(roots)
    uf = UnionFind(items)
    for i, left in enumerate(items):
        for right in items[i + 1:]:
            union = roots[left] | roots[right]
            inter = roots[left] & roots[right]
            if union and len(inter) / len(union) >= args.jaccard:
                uf.union(left, right)

    families = defaultdict(list)
    for root in items:
        families[uf.find(root)].append(root)

    rows = []
    for group in families.values():
        group = sorted(group)
        core = set.intersection(*(roots[root] for root in group))
        union = set.union(*(roots[root] for root in group))
        dims = []
        for root in group:
            box = boxes[root]
            dims.append(tuple(box[3 + i] - box[i] for i in range(3)) if box[0] < 1e9 else (0.0, 0.0, 0.0))
        avg_dim = tuple(sum(dim[i] for dim in dims) / len(dims) for i in range(3))
        rows.append((group, core, union, avg_dim))
    rows.sort(key=lambda item: (-len(item[0]), -len(item[1]), item[0]))

    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow([
            "family_id", "root_count", "roots", "min_bones", "max_bones",
            "core_bones", "union_bones", "variable_bones",
            "avg_dim_x", "avg_dim_y", "avg_dim_z",
        ])
        for index, (group, core, union, avg_dim) in enumerate(rows, start=1):
            writer.writerow([
                f"F{index:02d}", len(group), ",".join(group),
                min(len(roots[root]) for root in group),
                max(len(roots[root]) for root in group),
                len(core), len(union), len(union - core),
                *(f"{value:.6g}" for value in avg_dim),
            ])

    print(f"roots: {len(items)}; families: {len(rows)}; jaccard >= {args.jaccard}")
    print("family\troots\tmin\tmax\tcore\tunion\tavg_dim\troot_ids")
    for index, (group, core, union, avg_dim) in enumerate(rows, start=1):
        print(
            f"F{index:02d}\t{len(group)}\t"
            f"{min(len(roots[root]) for root in group)}\t"
            f"{max(len(roots[root]) for root in group)}\t"
            f"{len(core)}\t{len(union)}\t"
            f"{tuple(round(v, 3) for v in avg_dim)}\t{','.join(group)}"
        )


if __name__ == "__main__":
    main()
