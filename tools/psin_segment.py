"""Segment a PSIN record into rows of a fixed width.

A PSIN record is a flat run of `(value, type, property, key)` rows. Where the
rows form a table, the property column repeats with the row width; where four
records show 99.7-99.9 % agreement at width 4 or 6, and the largest record shows
none, the flat dump is a table *plus* whatever nesting got lost.

This tool turns that into something usable: it finds each record's width and cuts
the row stream into numbered rows, so a reader can see `row 12 = position, flags,
heading, ...` instead of 6,246 unlabelled lines.

    python3 tools/psin_segment.py --properties cache/psin-properties.tsv \\
        --out handoff/psin-segments.tsv --describe 1054
"""
import argparse
import csv
from collections import defaultdict
from pathlib import Path


def widths(props, limit=64):
    n = len(props)
    for width in range(2, min(limit, n // 2)):
        same = sum(1 for i in range(n - width) if props[i] == props[i + width])
        yield width, same / (n - width)


def best_width(props):
    if len(props) < 8:
        return None
    return max(widths(props), key=lambda item: item[1])


def label(row, names):
    return names.get(int(row["class_hash"], 16), row["class_hash"])


def show(row, names):
    """The row's content.

    For `Id`/`Type` rows the payload is the *key* (a string such as `CAR` or
    `location`), while the value column carries an ordinal. Prefer a resolved
    key, fall back to the raw value.
    """
    key = int(row["field_hash"], 16)
    if key in names:
        return names[key]
    value = row["value"]
    if row["type"] in ("0x103", "0x104"):
        try:
            value = names.get(int(value, 16), value)
        except ValueError:
            pass
    return value


def describe(rows, psin, names):
    """Print entries. Two-row entries (an id and its type) are paired.

    The alternation is local, not global: only one record in the corpus repeats
    with period 2 throughout, while segments of the large records alternate
    `Id`, `Type` for tens of rows before switching shape. So pairs are detected
    run by run rather than assumed.
    """
    print(f"record {psin}: {len(rows)} rows")
    index = 0
    printed = 0
    while index < len(rows) and printed < 400:
        row = rows[index]
        first = label(row, names)
        second = label(rows[index + 1], names) if index + 1 < len(rows) else None
        if second and first != second and index + 2 < len(rows) \
                and label(rows[index + 2], names) == first:
            value_a = show(row, names)
            value_b = show(rows[index + 1], names)
            print(f"  {printed:>5}  {first}={value_a:<34} {second}={value_b}")
            index += 2
        else:
            print(f"  {printed:>5}  {first}={show(row, names):<34} "
                  f"{names.get(int(row['field_hash'], 16), row['field_hash'])}")
            index += 1
        printed += 1
    print(f"  ... {index} of {len(rows)} rows shown" if index < len(rows) else "")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--properties", type=Path,
                        default=Path("cache/psin-properties.tsv"))
    parser.add_argument("--names", type=Path, default=Path("handoff/names.tsv"))
    parser.add_argument("--out", type=Path, default=Path("handoff/psin-segments.tsv"))
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument("--describe", help="print the rows of one record")
    args = parser.parse_args()

    names = {}
    if args.names.is_file():
        names = {int(r["hash"], 16): r["name"]
                 for r in csv.DictReader(args.names.open(), delimiter="\t")}
    by_record = defaultdict(list)
    for row in csv.DictReader(args.properties.open(), delimiter="\t"):
        by_record[row["psin"]].append(row)
    for rows in by_record.values():
        rows.sort(key=lambda r: int(r["offset"], 16))

    if args.describe:
        describe(by_record[args.describe], args.describe, names)
        return 0

    written = 0
    segmented = 0
    with args.out.open("w") as out:
        out.write("psin\tsegment\toffset\trows\twidth\tagreement\tproperties\n")
        for psin in sorted(by_record, key=lambda p: int(p)):
            rows = by_record[psin]
            props = [int(r["class_hash"], 16) for r in rows]
            found = best_width(props)
            if not found or found[1] < args.threshold:
                out.write(f"{psin}\t0\t{rows[0]['offset']}\t{len(rows)}\t0\t"
                          f"{found[1] if found else 0:.3f}\t\n")
                written += 1
                continue
            width, score = found
            segmented += 1
            for start in range(0, len(rows), width):
                block = rows[start:start + width]
                labels = []
                for row in block:
                    labels.append(names.get(int(row["class_hash"], 16),
                                            row["class_hash"]))
                out.write(f"{psin}\t{start // width}\t{block[0]['offset']}\t"
                          f"{len(block)}\t{width}\t{score:.3f}\t"
                          f"{','.join(labels)}\n")
                written += 1
    print(f"{len(by_record)} records: {segmented} segmented at >{args.threshold}, "
          f"{len(by_record) - segmented} left flat")
    print(f"{written} segments -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
