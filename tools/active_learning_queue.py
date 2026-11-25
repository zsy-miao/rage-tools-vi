#!/usr/bin/env python3
"""Build a representative/uncertain label queue from ML binary clusters."""
import argparse
import csv
from collections import defaultdict
from pathlib import Path


def first_nonzero(path, limit=64):
    data = Path(path).read_bytes()[:limit]
    offset = 0
    while offset < len(data) and data[offset] == 0:
        offset += 1
    return data[offset:offset + 8].hex(), offset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("details", type=Path, nargs="?", default=Path("output/packs-binary-clusters.tsv"))
    parser.add_argument("--out", type=Path, default=Path("handoff/packs-label-queue.tsv"))
    parser.add_argument("--per-cluster", type=int, default=4)
    args = parser.parse_args()

    clusters = defaultdict(list)
    with args.details.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            clusters[int(row["cluster"])].append(row)

    queue = []
    for cluster, items in sorted(clusters.items()):
        by_head = defaultdict(list)
        for row in items:
            head, offset = first_nonzero(row["path"])
            by_head[head].append((row, offset))
        chosen = []
        for head, group in sorted(by_head.items(), key=lambda item: -len(item[1])):
            group.sort(key=lambda item: int(item[0]["decoded_bytes"]))
            if group:
                chosen.append((head, group[len(group) // 2]))
            if len(chosen) >= args.per_cluster:
                break
        for rank, (head, (row, offset)) in enumerate(chosen, start=1):
            queue.append((
                cluster, rank, row["start"], row["decoded_bytes"], head, offset,
                row["path"], "", "label me",
            ))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow([
            "cluster", "rank", "start", "decoded_bytes", "head_after_zeros",
            "zero_offset", "path", "label", "note",
        ])
        writer.writerows(queue)
    print(f"clusters={len(clusters)} queue={len(queue)} -> {args.out}")


if __name__ == "__main__":
    main()
