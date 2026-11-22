#!/usr/bin/env python3
"""Verify a bulk extraction manifest against its range index and output files."""
import argparse
import csv
import hashlib
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("index", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", type=Path, default=Path("handoff/bulk-extraction-verification-summary.tsv"))
    parser.add_argument("--details", type=Path)
    parser.add_argument("--no-hash", action="store_true")
    args = parser.parse_args()

    index = {}
    with args.index.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["kind"] == "zlib":
                index[int(row["start"], 16)] = (int(row["end"], 16), int(row["decoded_bytes"] or 0))

    rows = []
    seen = set()
    failures = 0
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            start = int(row["start"], 16)
            path = Path(row["path"])
            seen.add(start)
            expected = index.get(start)
            size_ok = expected is not None and int(row["decoded_bytes"]) == expected[1]
            file_ok = path.is_file() and path.stat().st_size == int(row["decoded_bytes"])
            sha_ok = True
            if file_ok and not args.no_hash:
                sha_ok = digest(path) == row["sha256"]
            status = "PASS" if size_ok and file_ok and sha_ok else "FAIL"
            if status != "PASS":
                failures += 1
            rows.append((args.archive, start, expected[1] if expected else "", path.stat().st_size if path.is_file() else "", sha_ok, status))

    missing = set(index) - seen
    extra = seen - set(index)
    if missing or extra:
        failures += 1
    if args.details:
        args.details.parent.mkdir(parents=True, exist_ok=True)
        with args.details.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(["archive", "start", "expected_decoded", "actual_bytes", "sha_ok", "status"])
            writer.writerows(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        if args.out.stat().st_size == 0:
            writer.writerow(["archive", "manifest", "index", "missing", "extra", "failures", "status"])
        writer.writerow([args.archive, len(rows), len(index), len(missing), len(extra), failures, "PASS" if not failures and not missing and not extra else "FAIL"])
    print(
        f"{args.archive}: manifest={len(rows)} index={len(index)} missing={len(missing)} "
        f"extra={len(extra)} failures={failures}"
    )
    if failures or missing or extra:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
