"""Print PSIN records as readable rows, using the name registry.

The property array is `(value, type, property_hash, key_hash)`. Dumped raw it is
62,910 lines of hex; joined against `handoff/names.tsv` it becomes a script's
schema. This is the tool that makes the naming work usable.

    # one record, every row
    python3 tools/psin_dump.py --record 110

    # the largest record, first 20 rows
    python3 tools/psin_dump.py --record 1054 --limit 20

    # every record that mentions `position`
    python3 tools/psin_dump.py --property position

Needs `cache/psin-properties.tsv` (from the dump step) and
`handoff/names.tsv` (from `tools/name_registry.py --build`).
"""
import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

TYPES = {"0x101": "int", "0x102": "float", "0x103": "hash",
         "0x104": "bool", "0x105": "byte"}


def load_names(path):
    if not path.is_file():
        return {}
    return {int(r["hash"], 16): r["name"]
            for r in csv.DictReader(path.open(), delimiter="\t")}


def show(value, kind, names):
    if kind not in ("0x103", "0x104"):
        return str(value)
    try:
        number = int(value, 16)
    except (TypeError, ValueError):
        return str(value)
    return names.get(number, value)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--properties", type=Path,
                        default=Path("cache/psin-properties.tsv"))
    parser.add_argument("--names", type=Path, default=Path("handoff/names.tsv"))
    parser.add_argument("--record", help="PSIN record index")
    parser.add_argument("--property", help="only records mentioning this name")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if not args.properties.is_file():
        sys.exit(f"missing {args.properties}; produce it with the PSIN dump step")
    names = load_names(args.names)
    by_record = defaultdict(list)
    for row in csv.DictReader(args.properties.open(), delimiter="\t"):
        by_record[row["psin"]].append(row)

    if args.property:
        wanted = args.property.lower()
        hits = 0
        for psin, rows in sorted(by_record.items(), key=lambda kv: int(kv[0])):
            if any(names.get(int(r["class_hash"], 16), "").lower() == wanted for r in rows):
                print(f"record {psin}: {len(rows)} rows")
                hits += 1
        print(f"{hits} records mention {args.property!r}")
        return 0

    if not args.record:
        sizes = sorted(((len(v), k) for k, v in by_record.items()), reverse=True)
        print(f"{len(by_record)} records, {sum(len(v) for v in by_record.values())} rows")
        print("largest:", [(k, n) for n, k in sizes[:5]])
        return 0

    rows = sorted(by_record[args.record], key=lambda r: int(r["offset"], 16))
    if args.limit:
        rows = rows[:args.limit]
    print(f"record {args.record}: {len(by_record[args.record])} rows"
          + (f" (showing {len(rows)})" if args.limit else ""))
    print(f"{'offset':>8}  {'type':6} {'value':>12}  {'property':24} key")
    for row in rows:
        prop = names.get(int(row["class_hash"], 16), row["class_hash"])
        key = names.get(int(row["field_hash"], 16), row["field_hash"])
        value = show(row["value"], row["type"], names)
        print(f"{row['offset']:>8}  {TYPES.get(row['type'], row['type']):6} "
              f"{value:>12}  {prop:24} {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
