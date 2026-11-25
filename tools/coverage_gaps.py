#!/usr/bin/env python3
"""Report unclassified extraction spans by archive and largest gaps."""
import argparse
import csv
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventories", type=Path, nargs="*", default=[
        Path("output/extraction-inventory.tsv"), Path("output/archive-maps.tsv"),
    ])
    parser.add_argument("--ranges-out", type=Path, default=Path("output/unclassified-ranges.tsv"))
    parser.add_argument("--summary-out", type=Path, default=Path("handoff/unclassified-summary.tsv"))
    parser.add_argument("--md-out", type=Path, default=Path("handoff/unclassified-gaps.md"))
    args = parser.parse_args()

    gaps = defaultdict(list)
    for path in args.inventories:
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row["kind"] != "unclassified":
                    continue
                gaps[row["archive"]].append(row)

    args.ranges_out.parent.mkdir(parents=True, exist_ok=True)
    with args.ranges_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["archive", "start", "end", "stored_bytes", "source"])
        for archive, rows in sorted(gaps.items()):
            for row in rows:
                writer.writerow([archive, row["start"], row["end"], row["stored_bytes"], row.get("source", "")])

    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    with args.summary_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["archive", "ranges", "bytes", "largest_span", "largest_start"])
        for archive, rows in sorted(gaps.items()):
            total = sum(int(row["stored_bytes"]) for row in rows)
            largest = max(rows, key=lambda row: int(row["stored_bytes"]))
            writer.writerow([archive, len(rows), total, largest["stored_bytes"], largest["start"]])

    lines = ["# Unclassified extraction gaps", ""]
    lines.append("| Archive | Ranges | Bytes | Largest span | Largest start |")
    lines.append("| --- | ---: | ---: | ---: | --- |")
    for archive, rows in sorted(gaps.items()):
        total = sum(int(row["stored_bytes"]) for row in rows)
        largest = max(rows, key=lambda row: int(row["stored_bytes"]))
        lines.append(f"| `{archive}` | {len(rows):,} | {total:,} | {int(largest['stored_bytes']):,} | `{largest['start']}` |")
    lines += ["", "## Largest gaps", ""]
    for archive, rows in sorted(gaps.items()):
        top = sorted(rows, key=lambda row: -int(row["stored_bytes"]))[:8]
        lines.append(f"### `{archive}`")
        lines.append("")
        for row in top:
            lines.append(f"- `{row['start']}..{row['end']}` — {int(row['stored_bytes']):,} bytes")
        lines.append("")
    args.md_out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()
