"""Join the name registry onto every handoff table that carries hashes.

`name_registry.py --annotate` does one file with one named column. The handoff
directory has ~60 tables with hash columns under a dozen different names
(`bone_hash`, `id0`, `root_id`, `hash`, `pair_lo`, ...). This walks all of them,
detects hash columns by their values instead of their names, and writes an
annotated copy per file.

    python3 tools/annotate_handoff.py --out output/named \\
        --coverage handoff/name-coverage.tsv

Annotated copies are derivable, so they go under `output/` (untracked). The
coverage table is the committed artifact: it says, per file, how many rows and
hash columns exist and how many now carry a name.
"""
import argparse
import csv
import re
from pathlib import Path

HASH = re.compile(r"^0x[0-9a-fA-F]{8}$")


def load_registry(path):
    if not path.is_file():
        raise SystemExit(f"missing {path}; run tools/name_registry.py --build")
    return {int(row["hash"], 16): row
            for row in csv.DictReader(path.open(), delimiter="\t")}


def hash_columns(rows, limit=200):
    """Columns where most non-empty values look like 0x + 8 hex digits."""
    columns = []
    for name in rows[0]:
        values = [row[name] for row in rows[:limit] if (row.get(name) or "").strip()]
        if values and sum(1 for v in values if HASH.match(v.strip())) >= 0.9 * len(values):
            columns.append(name)
    return columns


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--handoff", type=Path, default=Path("handoff"))
    parser.add_argument("--registry", type=Path, default=Path("handoff/names.tsv"))
    parser.add_argument("--out", type=Path, default=Path("output/named"))
    parser.add_argument("--coverage", type=Path, default=Path("handoff/name-coverage.tsv"))
    args = parser.parse_args()

    registry = load_registry(args.registry)
    args.out.mkdir(parents=True, exist_ok=True)
    coverage = []
    for path in sorted(args.handoff.glob("*.tsv")):
        if path.name in ("names.tsv", "name-coverage.tsv"):
            continue
        rows = list(csv.DictReader(path.open(), delimiter="\t"))
        if not rows:
            continue
        columns = [c for c in hash_columns(rows) if c not in ("name",)]
        if not columns:
            continue
        total = len(rows) * len(columns)
        named = 0
        # Field names must be fixed before any row is touched: only rows that
        # actually carry a hash value get a `*_name` key, so deriving the header
        # from `rows[0]` afterwards fails as soon as the first row has no hash.
        fields = list(rows[0]) + [f"{column}_name" for column in columns]
        for row in rows:
            for column in columns:
                raw = (row.get(column) or "").strip()
                if not HASH.match(raw):
                    continue
                hit = registry.get(int(raw, 16))
                row[f"{column}_name"] = hit["name"] if hit else ""
                named += 1 if hit else 0
        for row in rows:
            for column in columns:
                row.setdefault(f"{column}_name", "")
        with (args.out / path.name).open("w") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t",
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        coverage.append((path.name, len(rows), len(columns), ",".join(columns),
                         named, total))

    args.coverage.parent.mkdir(parents=True, exist_ok=True)
    with args.coverage.open("w") as handle:
        handle.write("file\trows\thash_columns\tcolumns_named\tvalues_named\t"
                     "values_total\tshare\n")
        for name, rows, columns, names, named, total in coverage:
            share = named / total if total else 0.0
            handle.write(f"{name}\t{rows}\t{columns}\t{names}\t{named}\t{total}\t"
                         f"{share:.4f}\n")
    rows_named = sum(named for *_, named, _ in coverage)
    rows_total = sum(total for *_, total in coverage)
    print(f"{len(coverage)} tables annotated -> {args.out}")
    print(f"{rows_named:,} of {rows_total:,} hash values named "
          f"({rows_named / rows_total:.2%})" if rows_total else "no hash values")
    print(f"coverage written to {args.coverage}")
    for name, rows, columns, names, named, total in coverage:
        if named:
            print(f"  {name:42s} {named:>7,} / {total:>7,}  ({names})")


if __name__ == "__main__":
    main()
