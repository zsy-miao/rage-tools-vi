#!/usr/bin/env python3
"""Create a sparse RPF9-shaped fixture and matching index for UI tests."""
import argparse
from pathlib import Path
import struct


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--size", type=int, default=1024 * 1024 * 1024)
    args = parser.parse_args()
    if args.size <= 96:
        parser.error("size must exceed 96 bytes")
    args.directory.mkdir(parents=True, exist_ok=True)
    archive = args.directory / "sparse.rpf"
    index = args.directory / "sparse.tsv"
    header = bytearray(96)
    header[:4] = b"9FPR"
    struct.pack_into("<I", header, 4, 96)
    with archive.open("xb") as handle:
        handle.write(header)
        handle.truncate(args.size)
    with index.open("x", encoding="utf-8") as handle:
        handle.write("kind\tstart\tend\tstored_bytes\tdecoded_bytes\tchain_start\n")
        handle.write("front\t0x0\t0x60\t96\t\t\n")
        handle.write(f"unclassified\t0x60\t0x{args.size:x}\t{args.size - 96}\t\t\n")


if __name__ == "__main__":
    main()
