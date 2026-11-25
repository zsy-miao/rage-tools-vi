"""Reconcile declared RPF9 entry counts against observed payload items.

The header census gives every pack's declared entry count N.  Each nested pack
is one entry of exactly one parent, so summing N over every pack in a file must
equal the number of payload items at all levels plus the number of nested packs:

    sum(N) - (packs - roots) == items

where an item is one zlib chain (a 64 KiB continuation stream shares the
predecessor's chain) or one opaque span.  The residual is the number of declared
entries with no observed payload item, minus items nobody declared.

Chain detection follows the established continuation rule: a stream continues
its predecessor when the predecessor decoded exactly 65,536 bytes and the next
stream starts on the align16 boundary of its end.
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

CHUNK = 65536


def align16(value):
    return (value + 15) // 16 * 16


def load_census(path):
    packs = defaultdict(list)
    with path.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            packs[row["archive"]].append(int(row["count"]))
    return packs


def load_index(path):
    """Return (zlib chains, opaque spans, continuation count) for one index."""
    chains = 0
    continuations = 0
    opaque = 0
    previous = None
    with path.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["kind"] == "unclassified":
                opaque += 1
                continue
            if row["kind"] != "zlib":
                continue
            start = int(row["start"], 16)
            end = int(row["end"], 16)
            decoded = int(row["decoded_bytes"] or 0)
            continues = (
                previous is not None
                and previous[2] == CHUNK
                and start == align16(previous[1])
            )
            if continues:
                continuations += 1
            else:
                chains += 1
            previous = (start, end, decoded)
    return chains, opaque, continuations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, default=Path("handoff/header-census-full.tsv"))
    parser.add_argument("--index-dir", type=Path, default=Path("output/index"))
    parser.add_argument("--tsv", type=Path, default=Path("handoff/entry-reconciliation.tsv"))
    args = parser.parse_args()

    packs = load_census(args.census)
    rows = []
    for name in sorted(packs):
        key = name[:-4] if name.endswith(".rpf") else name
        index = args.index_dir / f"{key}.tsv"
        declared = sum(packs[name])
        count = len(packs[name])
        if not index.is_file():
            rows.append((name, count, declared, None, None, None, None, "index missing"))
            continue
        chains, opaque, continuations = load_index(index)
        items = chains + opaque
        nested = count - 1
        residual = declared - nested - items
        rows.append((name, count, declared, continuations, items, nested, residual, "ok"))

    print(f"{'archive':26s} {'packs':>5} {'sumN':>8} {'cont':>5} {'items':>8} "
          f"{'nested':>6} {'residual':>8}")
    for name, count, declared, continuations, items, nested, residual, note in rows:
        if note != "ok":
            print(f"{name:26s} {count:>5} {declared:>8} {'':>5} {'':>8} {'':>6} "
                  f"{'':>8}  {note}")
            continue
        print(f"{name:26s} {count:>5} {declared:>8} {continuations:>5} {items:>8} "
              f"{nested:>6} {residual:>+8}")

    total_declared = sum(row[2] for row in rows)
    total_items = sum(row[4] for row in rows if row[4] is not None)
    total_nested = sum(row[5] for row in rows if row[5] is not None)
    print(f"\nTOTAL declared {total_declared} items {total_items} nested {total_nested} "
          f"residual {total_declared - total_nested - total_items:+}")

    fields = ["archive", "packs", "declared", "continuations", "items", "nested", "residual"]
    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w") as out:
        out.write("\t".join(fields) + "\n")
        for row in rows:
            out.write("\t".join("" if value is None else str(value) for value in row[:7]) + "\n")
    print(f"wrote {args.tsv}")


if __name__ == "__main__":
    main()
