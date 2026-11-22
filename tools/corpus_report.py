"""Render `handoff/corpus-pass.tsv` into a docs page and a console table.

    python3 tools/corpus_report.py            # print
    python3 tools/corpus_report.py --write    # also write docs/extraction/corpus.md
"""
import argparse
import csv
from pathlib import Path


def load(path=Path("handoff/corpus-pass.tsv")):
    if not path.is_file():
        return []
    return list(csv.DictReader(path.open(), delimiter="\t"))


def gb(value):
    try:
        return f"{int(value) / 1e9:.1f}"
    except (TypeError, ValueError):
        return "—"


def pct(part, whole):
    try:
        part, whole = int(part), int(whole)
        return f"{part / whole:.0%}" if whole else "—"
    except (TypeError, ValueError):
        return "—"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", type=Path, default=Path("handoff/corpus-pass.tsv"))
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()

    rows = load(args.table)
    if not rows:
        print(f"{args.table} is missing or empty; run tools/corpus_pass.sh first")
        return 1

    lines = [
        "| Archive | Ranges | zlib | Stored GB | Packs | Exact model | Unit | Entries |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| `{row['archive']}` | {int(row['ranges']):,} | {int(row['zlib']):,} | "
            f"{gb(row['stored_bytes'])} | {row['packs'] or '—'} | "
            f"{pct(row['exact_packs'], row['packs'])} | {row['unit'] or '—'} | "
            f"{row['entries'] or '—'} |")
    total_ranges = sum(int(r["ranges"]) for r in rows)
    total_zlib = sum(int(r["zlib"]) for r in rows)
    total_stored = sum(int(r["stored_bytes"]) for r in rows)
    lines.append(f"| **total** | **{total_ranges:,}** | **{total_zlib:,}** | "
                 f"**{gb(total_stored)}** | | | | |")
    text = "\n".join(lines)
    print(text)

    if args.write:
        page = ["# Corpus pass", "",
                "Every `*.rpf` in the source directory, indexed and measured with the "
                "current tools. `Exact model` is the share of packs whose declared entry "
                "count is reproduced exactly by one of the simple entry models "
                "(`single`, `pairs`, `chains`, `structs-1`, `pos-pairs`); `Entries` is the "
                "payload-derived manifest size where one was emitted.", "",
                text, "",
                "Regenerate with `tools/corpus_pass.sh <source> --entries` and "
                "`python3 tools/corpus_report.py --write docs/extraction/corpus.md`.", ""]
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text("\n".join(page))
        print(f"\nwrote {args.write}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
