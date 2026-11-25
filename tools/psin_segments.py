"""Split a PSIN record where its table width changes.

A record is a run of `(value, type, property, key)` rows. Where the run is a table,
the property column repeats with the row width; where it is two nested tables, the
period changes at the boundary. So the tree is recoverable by *splitting on a
change of period* rather than by looking for a field.

The splitter is recursive: try one width for the whole span, and if the agreement
is below `--threshold`, halve the span and recurse. A span that never reaches the
threshold is emitted as `flat` (a leaf that is not a table).

    python3 tools/psin_segments.py --out handoff/psin-segments.tsv --describe 1054
"""
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


def widths(props, limit=64):
    n = len(props)
    for width in range(2, min(limit, n // 3)):
        same = sum(1 for i in range(n - width) if props[i] == props[i + width])
        yield width, same / (n - width)


def best(props):
    if len(props) < 12:
        return (None, 0.0)
    return max(widths(props), key=lambda item: item[1])


def split(props, threshold, minimum, depth=0, at=0):
    """Return a list of (start, rows, width, score) leaves."""
    width, score = best(props)
    if score >= threshold or len(props) < 2 * minimum or depth > 12:
        kind = width if score >= threshold else None
        return [(at, len(props), kind, score)]
    middle = (len(props) // 2) // minimum * minimum
    if middle < minimum:
        return [(at, len(props), None, score)]
    return (split(props[:middle], threshold, minimum, depth + 1, at)
            + split(props[middle:], threshold, minimum, depth + 1, at + middle))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--properties", type=Path,
                        default=Path("cache/psin-properties.tsv"))
    parser.add_argument("--out", type=Path, default=Path("handoff/psin-segments.tsv"))
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument("--minimum", type=int, default=8)
    parser.add_argument("--describe")
    args = parser.parse_args()

    by_record = defaultdict(list)
    for row in csv.DictReader(args.properties.open(), delimiter="\t"):
        by_record[row["psin"]].append(row)
    for rows in by_record.values():
        rows.sort(key=lambda r: int(r["offset"], 16))

    if args.describe:
        rows = by_record[args.describe]
        props = [int(r["class_hash"], 16) for r in rows]
        for start, count, width, score in split(props, args.threshold, args.minimum):
            print(f"  rows {start:>5}..{start+count-1:<5} "
                  f"({'table width %d' % width if width else 'flat'}) "
                  f"agreement {score:.3f}")
        return 0

    leaves = Counter()
    total = 0
    with args.out.open("w") as out:
        out.write("psin\tstart_row\trows\twidth\tagreement\n")
        for psin in sorted(by_record, key=lambda p: int(p)):
            rows = by_record[psin]
            props = [int(r["class_hash"], 16) for r in rows]
            if len(props) < 12:
                out.write(f"{psin}\t0\t{len(rows)}\t\t\n")
                leaves["tiny"] += 1
                continue
            for start, count, width, score in split(props, args.threshold, args.minimum):
                out.write(f"{psin}\t{start}\t{count}\t{width or ''}\t{score:.3f}\n")
                leaves["table" if width else "flat"] += 1
            total += 1
    print(f"{total} records segmented; leaves: {dict(leaves)} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
