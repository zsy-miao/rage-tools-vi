"""Extract every two-row entry from the PSIN property arrays.

Inside a record, consecutive rows often pair up: a field name and its value, an
`Id` and its `Type`. The pairing is local, so this walks each record and emits a
row whenever three consecutive property names alternate A, B, A.

    python3 tools/psin_entries.py --out handoff/psin-entries.tsv
"""
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


def label(row, names):
    return names.get(int(row["class_hash"], 16), row["class_hash"])


def content(row, names):
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


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--properties", type=Path,
                        default=Path("cache/psin-properties.tsv"))
    parser.add_argument("--names", type=Path, default=Path("handoff/names.tsv"))
    parser.add_argument("--out", type=Path, default=Path("handoff/psin-entries.tsv"))
    args = parser.parse_args()

    names = {}
    if args.names.is_file():
        names = {int(r["hash"], 16): r["name"]
                 for r in csv.DictReader(args.names.open(), delimiter="\t")}
    by_record = defaultdict(list)
    for row in csv.DictReader(args.properties.open(), delimiter="\t"):
        by_record[row["psin"]].append(row)

    counts = Counter()
    rows_out = []
    for psin in sorted(by_record, key=lambda p: int(p)):
        rows = sorted(by_record[psin], key=lambda r: int(r["offset"], 16))
        labels = [label(r, names) for r in rows]
        index = 0
        pair = 0
        while index < len(rows):
            if (index + 2 < len(rows)
                    and labels[index] != labels[index + 1]
                    and labels[index] == labels[index + 2]):
                first, second = rows[index], rows[index + 1]
                rows_out.append((psin, pair, labels[index], content(first, names),
                                 labels[index + 1], content(second, names)))
                counts[labels[index]] += 1
                counts[labels[index + 1]] += 1
                pair += 1
                index += 2
            else:
                index += 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as out:
        out.write("psin\tpair\tfield_a\tvalue_a\tfield_b\tvalue_b\n")
        for row in rows_out:
            out.write("\t".join(str(cell) for cell in row) + "\n")
    print(f"{len(rows_out)} entries -> {args.out}")
    print("field pairs:", Counter(
        (r[2], r[4]) for r in rows_out).most_common(8))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
