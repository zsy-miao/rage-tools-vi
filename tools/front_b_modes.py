"""Tabulate Front B size against 12N and 12(N+1), grouped by header mode."""

import argparse
import os
import struct
from collections import Counter, defaultdict
from pathlib import Path


def align16(value):
    return (value + 15) // 16 * 16


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data.rpf"))
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    size = os.path.getsize(args.data)
    rows = []
    with args.data.open("rb") as handle:
        for offset in range(0, size - 0x60, 0x1000):
            handle.seek(offset)
            header = handle.read(0x60)
            if len(header) < 0x60 or header[:4] != b"9FPR":
                continue
            front_end = struct.unpack_from("<I", header, 4)[0]
            block = struct.unpack_from("<I", header, 8)[0]
            trailer = struct.unpack_from("<I", header, 12)[0]
            count = struct.unpack_from("<I", header, 0x24)[0]
            if not (0x60 <= block <= front_end) or trailer > size - offset:
                continue
            size_b = front_end - block
            if size_b <= 0 or count == 0:
                continue
            mode = struct.unpack_from("<I", header, 0x20)[0]
            version = struct.unpack_from("<I", header, 0x2C)[0]
            rows.append((offset, count, size_b, mode, version))

    groups = defaultdict(list)
    for row in rows:
        groups[(row[3], row[4])].append(row)

    print(f"headers: {len(rows)}, modes: {len(groups)}")
    for (mode, version), records in sorted(groups.items(), key=lambda item: -len(item[1])):
        print(f"\nmode 0x{mode:08x} / 0x{version:08x}: {len(records)} headers")
        print("offset\tN\tNmod4\tB\talign16(10N)\talign16(12N)\talign16(12(N+1))\td10\tdN\tdN1")
        for offset, count, size_b, _, _ in records[: args.limit]:
            a10 = align16(10 * count)
            a = align16(12 * count)
            a1 = align16(12 * (count + 1))
            print(
                f"0x{offset:08x}\t{count}\t{count % 4}\t{size_b}\t{a10}\t{a}\t{a1}\t"
                f"{size_b - a10}\t{size_b - a}\t{size_b - a1}"
            )
        fits_10 = sum(1 for row in records if row[2] == align16(10 * row[1]))
        fits_n = sum(1 for row in records if row[2] == align16(12 * row[1]))
        fits_n1 = sum(1 for row in records if row[2] == align16(12 * (row[1] + 1)))
        print(
            f"fit: 10N {fits_10}/{len(records)}, 12N {fits_n}/{len(records)}, "
            f"12(N+1) {fits_n1}/{len(records)}"
        )
        print(f"N mod 4: {dict(Counter(row[1] % 4 for row in records))}")


if __name__ == "__main__":
    main()
