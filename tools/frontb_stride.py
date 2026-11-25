"""Recover the Front B row stride and the count at which it changes.

Front B is a table of `count` rows of `stride` bytes, padded to a 16-byte
boundary: `size_b == align16(stride * count)`. For a given header the stride can
be solved directly, and doing that across the whole census shows where the stride
steps from 9 to 10 bytes.

    python3 tools/frontb_stride.py --census handoff/header-census-full.tsv
"""
import argparse
import csv
from collections import Counter
from pathlib import Path


def align16(value):
    return (value + 15) // 16 * 16


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--census", type=Path,
                        default=Path("handoff/header-census-full.tsv"))
    parser.add_argument("--max-stride", type=int, default=20)
    args = parser.parse_args()

    solved = Counter()
    unambiguous = {9: [], 10: []}
    for row in csv.DictReader(args.census.open(), delimiter="\t"):
        try:
            count = int(row["count"])
            size = int(row["size_b"])
        except (KeyError, ValueError):
            continue
        if count <= 0 or size <= 0:
            continue
        fits = [s for s in range(4, args.max_stride + 1)
                if align16(s * count) == size]
        if not fits:
            solved["none"] += 1
            continue
        solved["solved"] += 1
        for stride in (9, 10):
            if fits == [stride]:
                unambiguous.setdefault(stride, []).append(count)

    print(f"headers with a stride in 4..{args.max_stride}: "
          f"{solved['solved']}, unsolved {solved['none']}")
    for stride in sorted(unambiguous):
        counts = unambiguous[stride]
        if not counts:
            continue
        counts.sort()
        print(f"stride {stride} only: {len(counts)} packs, "
              f"count {counts[0]}..{counts[-1]}")
    nine = unambiguous.get(9, [])
    ten = unambiguous.get(10, [])
    if nine and ten:
        print(f"\nboundary: stride 9 up to count {max(nine)}, "
              f"stride 10 from count {min(ten)}")
        print(f"the discriminating counts {max(nine) + 1}..{min(ten) - 1} "
              f"do not occur in this corpus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
