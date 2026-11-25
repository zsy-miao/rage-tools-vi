"""Measure the row width of each PSIN property array.

If a PSIN record's rows are a fixed-width table, the property column repeats
with a period equal to the width. This finds, for each record, the smallest
width whose property column agrees with itself shifted by that width, and
reports how many records reach a given agreement level.

    python3 tools/psin_table_width.py --properties cache/psin-properties.tsv
"""
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


def widths(props, limit=64):
    n = len(props)
    for width in range(2, min(limit, n // 2)):
        same = sum(1 for i in range(n - width) if props[i] == props[i + width])
        yield width, same / (n - width)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--properties", type=Path,
                        default=Path("cache/psin-properties.tsv"))
    parser.add_argument("--threshold", type=float, default=0.99)
    parser.add_argument("--minimum", type=int, default=40)
    args = parser.parse_args()

    by_record = defaultdict(list)
    for row in csv.DictReader(args.properties.open(), delimiter="\t"):
        by_record[row["psin"]].append(row)

    found = Counter()
    analysed = 0
    best_overall = []
    for psin, recs in by_record.items():
        recs.sort(key=lambda row: int(row["offset"], 16))
        props = [int(row["class_hash"], 16) for row in recs]
        if len(props) < args.minimum:
            continue
        analysed += 1
        top = max(widths(props), key=lambda item: item[1])
        best_overall.append((top[1], top[0], len(props), psin))
        for width, score in widths(props):
            if score > args.threshold:
                found[width] += 1
                break

    print(f"records analysed {analysed}")
    print(f"smallest width above {args.threshold}: "
          f"{found.most_common(8) if found else 'none'}")
    print(f"records reaching the threshold: {sum(found.values())}")
    best_overall.sort(reverse=True)
    print("strongest periodic records:")
    for score, width, rows, psin in best_overall[:6]:
        print(f"  width {width:>3}  agreement {score:.3f}  rows {rows:>5}  psin {psin}")


if __name__ == "__main__":
    main()
