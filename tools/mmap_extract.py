#!/usr/bin/env python3
"""Bounded-memory selective zlib extraction using a read-only mmap."""
import argparse
import hashlib
import mmap
import resource
import time
import zlib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--start", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--end", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with args.archive.open("rb") as handle:
        mm = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        started = time.monotonic()
        decoded = zlib.decompress(mm[args.start:args.end])
        elapsed = time.monotonic() - started
        mm.close()
    args.output.write_bytes(decoded)
    print(
        f"{args.archive} {args.start:#x}..{args.end:#x}: {len(decoded)} bytes "
        f"in {elapsed:.4f}s rss={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}KiB "
        f"sha256={hashlib.sha256(decoded).hexdigest()}"
    )


if __name__ == "__main__":
    main()
