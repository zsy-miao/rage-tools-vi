"""Assemble `handoff/corpus-pass.tsv` from the per-archive products.

Each archive's index gives ranges, zlib count and stored bytes; the header census
gives the declared entry count; `handoff/corpus-pass/pack-model-<name>.tsv` gives
how many packs fit an exact model; and `entries-<name>.tsv`, when present, gives
the payload-derived manifest size.

    python3 tools/corpus_table.py
"""
import csv
from pathlib import Path

WORK = Path("handoff/corpus-pass")


def main():
    declared = {}
    census = Path("handoff/header-census-full.tsv")
    if census.is_file():
        for row in csv.DictReader(census.open(), delimiter="\t"):
            try:
                declared[row["archive"]] = declared.get(row["archive"], 0) + int(row["count"])
            except (KeyError, ValueError):
                pass

    rows = []
    for index in sorted(Path("output/index").glob("*.tsv")):
        name = index.stem
        ranges = zlib = stored = 0
        for row in csv.DictReader(index.open(), delimiter="\t"):
            ranges += 1
            stored += int(row["stored_bytes"] or 0)
            if row["kind"] == "zlib":
                zlib += 1
        total = declared.get(f"{name}.rpf", 0)
        ratio = zlib / total if total else 0
        unit = ("pairs" if 1.6 <= ratio <= 2.4 else
                "single" if abs(ratio - 1) < 0.08 else
                "chains" if ratio > 1 else "")
        model = WORK / f"pack-model-{name}.tsv"
        packs = exact = ""
        if model.is_file():
            lines = [r for r in csv.DictReader(model.open(), delimiter="\t")]
            packs = len(lines)
            exact = sum(1 for r in lines if r["exact_models"] != "-")
        entries_file = WORK / f"entries-{name}.tsv"
        entries = ""
        if entries_file.is_file():
            entries = sum(1 for _ in entries_file.open()) - 1
        rows.append((f"{name}.rpf", ranges, zlib, total, stored, packs, exact, unit, entries))

    with Path("handoff/corpus-pass.tsv").open("w") as out:
        out.write("archive\tranges\tzlib\tdeclared\tstored_bytes\tpacks\t"
                  "exact_packs\tunit\tentries\n")
        for row in rows:
            out.write("\t".join(str(c) for c in row) + "\n")
    print(f"{len(rows)} archives -> handoff/corpus-pass.tsv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
