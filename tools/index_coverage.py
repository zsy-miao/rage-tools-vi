"""Report how much of each archive is classified, merging side indexes.

Every archive has `output/index/<name>.tsv`. Some also have side indexes produced by
a specialised pass — `<name>-adat.tsv` from `tools/adat_index.py` — which cover bytes
the main partitioner leaves as `unclassified`. This merges them and reports, per
archive:

  * total bytes and the share classified as anything other than `unclassified`;
  * the union actually covered by rows (so a side index does not double-count);
  * what is left, in bytes and percent.

    python3 tools/index_coverage.py
    python3 tools/index_coverage.py --out handoff/index-coverage.tsv
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "output" / "index"


def load(path):
    rows = []
    with path.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            try:
                rows.append((int(row["start"], 16), int(row["end"], 16), row["kind"]))
            except (KeyError, ValueError):
                continue
    return rows


def union(rows):
    total = 0
    current = None
    for start, stop, _kind in sorted(rows):
        if start >= stop:
            continue
        if current is None:
            current = [start, stop]
        elif start <= current[1]:
            current[1] = max(current[1], stop)
        else:
            total += current[1] - current[0]
            current = [start, stop]
    if current is not None:
        total += current[1] - current[0]
    return total


def report():
    archives = {}
    for path in sorted(INDEX.glob("*.tsv")):
        name = path.stem
        side = None
        if "-" in name:
            base, suffix = name.split("-", 1)
            if suffix and (INDEX / f"{base}.tsv").is_file():
                side = base
        rows = load(path)
        if side:
            archives.setdefault(side, []).append((name, rows))
        else:
            # append, do not setdefault: a side index processed first has already
            # created this key, and setdefault would silently drop the main rows.
            archives.setdefault(name, []).append((name, rows))
    out = []
    for name, parts in sorted(archives.items()):
        # A side index can be processed before its main file; fall back to whatever
        # rows exist rather than assuming the main one is present in the list.
        main_rows = next((rows for part, rows in parts if part == name), parts[0][1])
        total = max((stop for _s, stop, _k in main_rows), default=0)
        if not total:
            continue
        classified = sum(stop - start for start, stop, kind in main_rows
                         if kind != "unclassified")
        merged = []
        for _part, rows in parts:
            merged.extend(rows)
        covered = union(merged)
        classified_with_sides = sum(stop - start for start, stop, kind in merged
                                    if kind != "unclassified")
        out.append({
            "archive": name,
            "size": total,
            "main_classified": classified,
            "merged_classified": classified_with_sides,
            "union_covered": covered,
            "sides": ",".join(part for part, _rows in parts if part != name) or "-",
        })
    out.sort(key=lambda row: row["union_covered"] / row["size"])
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    rows = report()
    if not rows:
        sys.exit("no indexes under output/index")
    header = f"{'archive':26s} {'size':>13s} {'main kind':>9s} {'merged':>8s} {'covered':>8s}  sides"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(f"{row['archive']:26s} {row['size']:13,d} "
              f"{row['main_classified'] / row['size']:8.2%} "
              f"{row['merged_classified'] / row['size']:7.2%} "
              f"{row['union_covered'] / row['size']:7.2%}  {row['sides']}")
    total = sum(row["size"] for row in rows)
    covered = sum(row["union_covered"] for row in rows)
    print("-" * len(header))
    print(f"{'total':26s} {total:13,d} {'':8s} {'':7s} {covered / total:7.2%}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as handle:
            handle.write("archive\tsize\tmain_classified\tmerged_classified\t"
                         "union_covered\tsides\n")
            for row in rows:
                handle.write(f"{row['archive']}\t{row['size']}\t{row['main_classified']}\t"
                             f"{row['merged_classified']}\t{row['union_covered']}\t"
                             f"{row['sides']}\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
