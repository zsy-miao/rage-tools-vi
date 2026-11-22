#!/usr/bin/env python3
"""Probe the dominant u16_4042 packs stream header."""
import argparse
import csv
import struct
from collections import Counter
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("details", type=Path, nargs="?", default=Path("output/packs-signatures.tsv"))
    parser.add_argument("--tsv", type=Path, default=Path("handoff/packs-4042-probe.tsv"))
    args = parser.parse_args()

    sizes = Counter()
    fields = [Counter() for _ in range(8)]
    offset_hits = [0] * 8
    samples = []
    rows = 0
    with args.details.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["kind"] != "u16_4042":
                continue
            rows += 1
            size = int(row["decoded_bytes"])
            sizes[size] += 1
            with open(row["path"], "rb") as stream:
                head = stream.read(64)
            if len(head) < 40:
                continue
            values = struct.unpack_from("<Q8I", head)
            for index in range(8):
                fields[index][values[index]] += 1
                if 0 < values[index] < size:
                    offset_hits[index] += 1
            if len(samples) < 5:
                samples.append((row["path"], size, [hex(value) for value in values]))

    with args.tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["metric", "value", "count"])
        for size, count in sizes.most_common(20):
            writer.writerow(["size", size, count])
        for index in range(8):
            for value, count in fields[index].most_common(5):
                writer.writerow([f"word_{index}", f"0x{value:08x}", count])
        for index in range(8):
            writer.writerow([f"plausible_offset_{index}", offset_hits[index], rows])

    print(f"streams={rows} unique_sizes={len(sizes)}")
    print("top sizes", sizes.most_common(10))
    for index in range(8):
        print(f"word_{index}", [f"0x{v:08x}:{c}" for v, c in fields[index].most_common(3)], "offset_hits", offset_hits[index])
    for sample in samples:
        print(sample)


if __name__ == "__main__":
    main()
