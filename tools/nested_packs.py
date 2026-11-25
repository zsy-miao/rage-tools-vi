"""Every occurrence of the pack magic inside an archive, and what it turned out to be.

The archive class creates archives over bounded sub-streams, so a child pack inside a
parent is expected to exist. This scan finds every `0x52504639` (`9FPR`) at a 4-byte
boundary and reports the header fields beside it.

Measured on the twelve top-level archives: 4,356 candidates, 3,429 with a consistent
header, and **98.75 % of those sit on a 0x1000 boundary** — they are the pack starts the
index already knows, counted once more by a byte scan. The tool therefore answers the
question negatively for the top level: no pack header was found at a page-unaligned
offset, which is what a nested child archive would look like.

A candidate is reported as `plausible` when the front region and the arena fields are
consistent with the layout recovered for the top-level packs.

    python3 tools/nested_packs.py --source <dir> --out handoff/nested-packs.tsv
    python3 tools/nested_packs.py --archive levels.rpf
"""

import argparse
import csv
import os
import struct
import sys
from pathlib import Path

MAGIC = 0x52504639
CHUNK = 8 << 20


def scan(path, first=0x40):
    """Yield (offset, header words) for every pack magic at a 4-byte boundary."""
    size = path.stat().st_size
    with path.open("rb") as handle:
        position = first
        while position < size:
            handle.seek(position)
            chunk = handle.read(CHUNK + 4)
            if not chunk:
                break
            index = 0
            while True:
                found = chunk.find(b"9FPR", index)
                if found < 0:
                    break
                index = found + 1
                offset = position + found
                if offset % 4:
                    continue
                handle.seek(offset)
                header = handle.read(0x30)
                if len(header) < 0x30:
                    continue
                words = struct.unpack_from("<12I", header)
                yield offset, words, header
            position += CHUNK


def classify(words, header, offset, size):
    front, second, trailer = words[1], words[2], words[3]
    p3 = struct.unpack_from("<H", header, 0x1A)[0]
    p4 = words[7]
    p5 = struct.unpack_from("<H", header, 0x20)[0]
    reasons = []
    if front < 0x40 or front > size - offset:
        reasons.append("front")
    if not 1 <= p3 <= 64:
        reasons.append("p3")
    if not 0 < p4 <= 4096:
        reasons.append("p4")
    if not 1 <= p5 <= 64:
        reasons.append("p5")
    if trailer > front:
        reasons.append("trailer")
    return ("plausible" if not reasons else "rejected"), reasons


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    if args.archive:
        archives = [args.archive]
    elif args.source:
        archives = sorted(args.source.rglob("*.rpf"))
    else:
        parser.error("give --source or --archive")

    rows = []
    for archive in archives:
        size = archive.stat().st_size
        found = 0
        for offset, words, header in scan(archive):
            if offset == 0:
                continue
            verdict, reasons = classify(words, header, offset, size)
            rows.append((archive.name, hex(offset), verdict,
                         hex(words[1]), words[2], words[3],
                         ",".join(reasons) or "-"))
            found += 1
        print(f"{archive.name:34s} {size:>13,} B  nested candidates {found}")

    print()
    plausible = sum(1 for row in rows if row[2] == "plausible")
    print(f"{plausible} plausible of {len(rows)} candidates")
    for row in rows[:10]:
        print("  " + "  ".join(str(cell) for cell in row))
    if args.out and rows:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(["archive", "offset", "verdict", "front", "word_08",
                             "trailer", "reasons"])
            writer.writerows(rows)
        print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
