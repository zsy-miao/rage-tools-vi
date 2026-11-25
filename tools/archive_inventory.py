#!/usr/bin/env python3
"""Normalize Rust map output for the small local archives."""
import argparse
import csv
from collections import defaultdict
from pathlib import Path
import subprocess

DEFAULT_ARCHIVES = (
    Path("common.rpf"),
    Path("script.rpf"),
    Path("story000_bvh4.rpf"),
    Path("appdata0.rpf"),
    Path("core_licenses_data.rpf"),
    Path("shaders.rpf"),
    Path("textures.rpf"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", type=Path, nargs="*", default=list(DEFAULT_ARCHIVES))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--ranges-out", type=Path, default=Path("output/archive-maps.tsv"))
    parser.add_argument("--summary-out", type=Path, default=Path("handoff/archive-inventory-summary.tsv"))
    args = parser.parse_args()

    rows = []
    totals = defaultdict(lambda: [0, 0, 0])
    for archive in args.archives:
        if not archive.is_file():
            print(f"skip missing {archive}")
            continue
        result = subprocess.run(
            [str(args.cli), "map", str(archive)],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise SystemExit(f"{archive}: {result.stderr.strip()}")
        parsed = list(csv.DictReader(result.stdout.splitlines(), delimiter="\t"))
        if not parsed:
            raise SystemExit(f"{archive}: empty map")
        size = archive.stat().st_size
        cursor = 0
        for row in parsed:
            start = int(row["start"], 16)
            end = int(row["end"], 16)
            stored = int(row["stored_bytes"])
            decoded = int(row["decoded_bytes"] or 0)
            if start != cursor or end <= start or end - start != stored:
                raise SystemExit(f"{archive}: broken coverage at {cursor:#x}")
            cursor = end
            kind = row["kind"]
            rows.append((str(archive), kind, start, end, stored, decoded, "rage-tools-vi map"))
            totals[(str(archive), kind)][0] += 1
            totals[(str(archive), kind)][1] += stored
            totals[(str(archive), kind)][2] += decoded
        if cursor != size:
            raise SystemExit(f"{archive}: map ended at {cursor}, file is {size}")

    args.ranges_out.parent.mkdir(parents=True, exist_ok=True)
    with args.ranges_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["archive", "kind", "start", "end", "stored_bytes", "decoded_bytes", "source"])
        for row in rows:
            writer.writerow([
                row[0], row[1], f"0x{row[2]:x}", f"0x{row[3]:x}", row[4], row[5], row[6],
            ])

    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    with args.summary_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["archive", "kind", "ranges", "stored_bytes", "decoded_bytes"])
        for (archive, kind), values in sorted(totals.items()):
            writer.writerow([archive, kind, *values])

    print("archive\tkind\tranges\tstored_bytes\tdecoded_bytes")
    for (archive, kind), values in sorted(totals.items()):
        print(archive, kind, *values, sep="\t")
    print("total", len(rows), sum(v[1] for v in totals.values()), sum(v[2] for v in totals.values()), sep="\t")


if __name__ == "__main__":
    main()
