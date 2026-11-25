#!/usr/bin/env python3
"""Parallel bounded-memory extraction of every zlib span in an index."""
import argparse
import csv
import hashlib
import mmap
import os
import time
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

MM = None


def extract_one(task):
    start, end, expected, outdir = task
    decoded = zlib.decompress(MM[start:end])
    digest = hashlib.sha256(decoded).hexdigest()
    shard = Path(outdir) / f"{start >> 24:02x}"
    shard.mkdir(parents=True, exist_ok=True)
    path = shard / f"{start:016x}.bin"
    path.write_bytes(decoded)
    return start, end, end - start, len(decoded), digest, str(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("index", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--archive-name")
    parser.add_argument("--batch", type=int, default=4096)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    rows = []
    with args.index.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["kind"] != "zlib":
                continue
            if args.archive_name and row.get("archive") and row["archive"] != args.archive_name:
                continue
            rows.append((int(row["start"], 16), int(row["end"], 16), int(row["decoded_bytes"] or 0)))
    if args.limit:
        rows = rows[: args.limit]

    global MM
    manifest = args.manifest or (args.out_dir / "manifest.tsv")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    done = 0
    skipped = 0
    decoded_total = 0
    stored_total = 0
    with args.archive.open("rb") as handle:
        MM = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        if hasattr(MM, "madvise"):
            try:
                MM.madvise(mmap.MADV_RANDOM)
            except OSError:
                pass
        with manifest.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output, delimiter="\t", lineterminator="\n")
            writer.writerow(["start", "end", "stored_bytes", "decoded_bytes", "sha256", "path"])
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                for offset in range(0, len(rows), args.batch):
                    batch = rows[offset:offset + args.batch]
                    futures = []
                    for start, end, expected in batch:
                        path = args.out_dir / f"{start >> 24:02x}" / f"{start:016x}.bin"
                        if args.resume and path.is_file() and path.stat().st_size == expected:
                            digest = hashlib.sha256(path.read_bytes()).hexdigest()
                            writer.writerow([f"0x{start:x}", f"0x{end:x}", end - start, expected, digest, str(path)])
                            decoded_total += expected
                            stored_total += end - start
                            done += 1
                            skipped += 1
                        else:
                            futures.append(pool.submit(extract_one, (start, end, expected, str(args.out_dir))))
                    for future in as_completed(futures):
                        start, end, stored, decoded, digest, path = future.result()
                        writer.writerow([f"0x{start:x}", f"0x{end:x}", stored, decoded, digest, path])
                        stored_total += stored
                        decoded_total += decoded
                        done += 1
                    output.flush()
                    if hasattr(MM, "madvise"):
                        try:
                            MM.madvise(mmap.MADV_DONTNEED)
                        except OSError:
                            pass
        MM.close()
    elapsed = time.monotonic() - started
    print(
        f"streams={done} skipped={skipped} stored={stored_total} "
        f"decoded={decoded_total} elapsed={elapsed:.2f}s workers={args.workers} manifest={manifest}"
    )


if __name__ == "__main__":
    main()
