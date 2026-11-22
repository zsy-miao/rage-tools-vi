#!/usr/bin/env python3
"""Probe the 0f000080 packs family: sizes, header words, and 16-bit texture."""
import argparse
import csv
import math
import struct
from collections import Counter
from pathlib import Path


def entropy(data):
    counts = Counter(data)
    total = len(data)
    return -sum((count / total) * math.log2(count / total) for count in counts.values()) if total else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("details", type=Path, nargs="?", default=Path("output/packs-signatures.tsv"))
    parser.add_argument("--tsv", type=Path, default=Path("handoff/packs-0f000080-probe.tsv"))
    args = parser.parse_args()

    sizes = Counter()
    words = [Counter() for _ in range(8)]
    ranges = [(0xFFFF, 0)] * 4
    samples = []
    rows = 0
    with args.details.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["kind"] != "0f000080":
                continue
            rows += 1
            size = int(row["decoded_bytes"])
            sizes[size] += 1
            with open(row["path"], "rb") as stream:
                data = stream.read()
            for index in range(8):
                words[index][struct.unpack_from("<I", data, index * 4)[0]] += 1
            body = data[0x20:]
            for index in range(4):
                values = [struct.unpack_from("<H", body, pos)[0] for pos in range(index * 2, len(body) - 1, 8)]
                if values:
                    low, high = min(values), max(values)
                    ranges[index] = (min(ranges[index][0], low), max(ranges[index][1], high))
            if len(samples) < 5:
                samples.append((row["path"], size, f"{entropy(data):.4f}", data[:32].hex()))

    with args.tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value", "count"])
        for size, count in sizes.most_common(20):
            writer.writerow(["size", size, count])
        for index in range(8):
            for value, count in words[index].most_common(6):
                writer.writerow([f"word_{index}", f"0x{value:08x}", count])
        for index, (low, high) in enumerate(ranges):
            writer.writerow([f"u16_stride8_{index}", f"{low}..{high}", ""])

    print(f"streams={rows}; sizes={len(sizes)}")
    print("top sizes", sizes.most_common(10))
    for index in range(8):
        print(f"word_{index}", [f"0x{v:08x}:{c}" for v, c in words[index].most_common(4)])
    print("u16 ranges", ranges)
    for sample in samples:
        print(sample)


if __name__ == "__main__":
    main()
