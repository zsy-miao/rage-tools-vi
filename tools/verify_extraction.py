#!/usr/bin/env python3
"""Verify the general extraction entry point against known manifests."""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def first_map_row(path, archive, kind):
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["archive"] == archive and row["kind"] == kind:
                return row
    return None


def data_row(ranges, kind, with_hash):
    with ranges.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["kind"] == kind and (not with_hash or row.get("stored_sha256") or row.get("decoded_sha256")):
                return row
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("handoff/extraction-entry-verification.tsv"))
    parser.add_argument("--log", type=Path, default=Path("output/verification-log.jsonl"))
    args = parser.parse_args()

    cases = [
        ("script.rpf", "zlib", "0x53000", "0xc3b45", 2702384, "592afd44c211a8d07ca7f90ef3f8659d272b2d271b5a9a85ed735a5ed80c3c82"),
        ("script.rpf", "raw", "0x2010", "0x52fe0", 331728, "b5d622ca79058af2578b753002899ebc8b89b09d09edf1fc8071bc84bb4dc28e"),
    ]

    ranges = Path("output/data.rpf/ranges.tsv")
    row = data_row(ranges, "zlib", True)
    if row:
        cases.append(("data.rpf", "zlib", row["start"], row["end"], int(row["decoded_bytes"] or 0), row["decoded_sha256"]))
    row = data_row(ranges, "unclassified", True)
    if row:
        cases.append(("data.rpf", "raw", row["start"], row["end"], int(row["stored_bytes"]), row["stored_sha256"]))

    maps = Path("output/archive-maps.tsv")
    for archive in ("common.rpf", "story000_bvh4.rpf"):
        row = first_map_row(maps, archive, "zlib")
        if row:
            cases.append((archive, "zlib", row["start"], row["end"], int(row["decoded_bytes"] or 0), None))

    rows = []
    for archive, kind, start, end, expected_size, expected_sha in cases:
        output = Path(f"/tmp/verify-{archive.replace('.', '-')}-{start}.bin")
        output.unlink(missing_ok=True)
        command = [
            sys.executable, "tools/extract_entry.py",
            "--archive", archive, "--kind", kind, "--start", start, "--end", end,
            "--output", str(output), "--log", str(args.log),
        ]
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode != 0:
            rows.append((archive, kind, start, end, expected_size, "error", "sha256", "FAIL"))
            continue
        payload = output.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        size_ok = len(payload) == expected_size
        sha_ok = expected_sha is None or digest == expected_sha
        status = "PASS" if size_ok and sha_ok else "FAIL"
        rows.append((archive, kind, start, end, expected_size, len(payload), digest, status))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["archive", "kind", "start", "end", "expected_bytes", "actual_bytes", "sha256", "status"])
        writer.writerows(rows)
    for row in rows:
        print(*row, sep="\t")
    if any(row[-1] != "PASS" for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
