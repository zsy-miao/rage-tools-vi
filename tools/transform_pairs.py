#!/usr/bin/env python3
"""Test whether 48-byte transform entries pair by index and high byte."""
import argparse
from collections import Counter
import math
from pathlib import Path
import struct
import subprocess
import tempfile

OBJECT_START, OBJECT_END = 0x53000, 0xC3B45
TAG = 0x1EBB416B


def extract_object(cli, archive):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "object.bin"
        subprocess.run(
            [str(cli), "extract-zlib", str(archive), f"{OBJECT_START:x}", f"{OBJECT_END:x}", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        return path.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    count = struct.unpack_from("<I", data, 0x14)[0]
    offsets = struct.unpack_from(f"<{count}Q", data, 0x28)

    arrays = []
    for index, offset in enumerate(offsets):
        end = offsets[index + 1] if index + 1 < count else len(data)
        size = end - offset
        if size < 48:
            continue
        header = struct.unpack_from("<12I", data, offset)
        used, stride = header[5], header[6]
        body = size - 48
        if header[10] != TAG or not stride or used * stride > body or body - used * stride >= 16:
            continue
        entries = []
        for i in range(used):
            base = offset + 48 + i * stride
            xyz = struct.unpack_from("<3f", data, base)
            ident = struct.unpack_from("<I", data, base + 0x20)[0]
            entries.append((ident >> 8, ident & 0xFF, xyz))
        arrays.append((index, entries))

    pair_arrays = 0
    pair_total = 0
    distances = []
    examples = []
    high_counts = Counter()
    count_dist = Counter()
    for index, entries in arrays:
        count_dist[len(entries)] += 1
        by_index = {}
        for high, low, xyz in entries:
            high_counts[high] += 1
            by_index.setdefault(low, {})[high] = xyz
        found = 0
        for low, values in by_index.items():
            if 1 in values and 2 in values:
                a, b = values[1], values[2]
                distance = math.dist(a, b)
                distances.append(distance)
                found += 1
                pair_total += 1
                if len(examples) < args.limit:
                    examples.append((index, low, distance, a, b))
        if found:
            pair_arrays += 1

    print(f"arrays: {len(arrays)}; arrays with a 1/2 pair: {pair_arrays}; pairs: {pair_total}")
    print(f"entry count distribution: {count_dist.most_common(12)}")
    print(f"high-byte counts: {high_counts}")
    if distances:
        ordered = sorted(distances)
        print(
            "distance min/median/p90/max: "
            f"{ordered[0]:.5g}/{ordered[len(ordered)//2]:.5g}/"
            f"{ordered[int(len(ordered)*0.9)]:.5g}/{ordered[-1]:.5g}"
        )
        buckets = Counter(round(d, 3) for d in distances)
        print("distance buckets:", buckets.most_common(12))
    print("\npair examples")
    for index, low, distance, a, b in examples:
        print(
            f"  rec {index} index {low} dist={distance:.5g} "
            f"high1=({a[0]:.5g},{a[1]:.5g},{a[2]:.5g}) "
            f"high2=({b[0]:.5g},{b[1]:.5g},{b[2]:.5g})"
        )


if __name__ == "__main__":
    main()
