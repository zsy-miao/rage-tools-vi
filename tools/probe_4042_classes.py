#!/usr/bin/env python3
"""Compare u16_4042 size classes by entropy and byte regularity."""
import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path


def entropy(data):
    counts = Counter(data)
    total = len(data)
    return -sum((count / total) * math.log2(count / total) for count in counts.values()) if total else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("details", type=Path, nargs="?", default=Path("output/packs-signatures.tsv"))
    parser.add_argument("--tsv", type=Path, default=Path("handoff/packs-4042-classes.tsv"))
    args = parser.parse_args()

    groups = defaultdict(list)
    with args.details.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["kind"] == "u16_4042":
                groups[int(row["decoded_bytes"])].append(row)

    rows = []
    for size, items in sorted(groups.items(), key=lambda item: -len(item[1]))[:20]:
        sample = Path(items[0]["path"]).read_bytes()[:65536]
        zeros = sample.count(0) / len(sample)
        adjacent = sum(1 for i in range(1, len(sample)) if sample[i] == sample[i - 1]) / (len(sample) - 1)
        rows.append((size, len(items), f"{entropy(sample):.4f}", f"{zeros:.4f}", f"{adjacent:.4f}"))
    with args.tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["size", "streams", "entropy", "zero_fraction", "adjacent_equal"])
        writer.writerows(rows)
    print("size\tstreams\tentropy\tzero_fraction\tadjacent_equal")
    for row in rows:
        print(*row, sep="\t")


if __name__ == "__main__":
    main()
