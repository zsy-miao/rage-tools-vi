"""Probe story000_bvh4.rpf Front A for known payload ranges and simple transforms."""

import argparse
from collections import Counter
import math
from pathlib import Path
import struct


def entropy(data):
    counts = [0] * 256
    for byte in data:
        counts[byte] += 1
    return -sum(
        (count / len(data)) * math.log2(count / len(data))
        for count in counts
        if count
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("story000_bvh4.rpf"))
    args = parser.parse_args()
    data = args.archive.read_bytes()
    front_end = struct.unpack_from("<I", data, 4)[0]
    front_block = struct.unpack_from("<I", data, 8)[0]
    front_a = data[0x60:front_block]
    print(f"front A: 0x60..0x{front_block:x}, {len(front_a)} bytes")
    print(f"entropy: first 256 {entropy(front_a[:0x100]):.4f}, rest {entropy(front_a[0x100:]):.4f}")
    blocks = [front_a[index : index + 16] for index in range(0, len(front_a) // 16 * 16, 16)]
    counts = Counter(blocks)
    print(f"16-byte blocks: {len(blocks)}, unique {len(counts)}, repeated {sum(1 for n in counts.values() if n > 1)}")

    payload = (0x340, 0x1000, 0x12A0, 0x13C0)
    stored = (0x4F1 - 0x340, 0x1291 - 0x1000, 0x13BD - 0x12A0, 0x1564 - 0x13C0)
    decoded = (800, 14426, 622, 829)
    values = {}
    for index, value in enumerate(payload):
        values[f"offset{index}"] = value
        values[f"stored{index}"] = stored[index]
        values[f"decoded{index}"] = decoded[index]
        if value % 16 == 0:
            values[f"offset{index}/16"] = value // 16
    print("known values:", ", ".join(f"{name}={value:#x}" for name, value in values.items()))

    def search(label, value):
        for width in (4, 8):
            for order in ("little", "big"):
                position = front_a.find(value.to_bytes(width, order))
                if position >= 0:
                    print(f"MATCH {label} {value:#x} width {width} {order} at 0x{position:x}")

    for name, value in values.items():
        search(name, value)
    for group_name, group in (("offset", payload), ("stored", stored), ("decoded", decoded)):
        for left in range(len(group)):
            for right in range(left + 1, len(group)):
                for label, value in (
                    ("diff", abs(group[left] - group[right])),
                    ("xor", group[left] ^ group[right]),
                    ("sum", group[left] + group[right]),
                ):
                    search(f"{group_name}-{label}", value)


if __name__ == "__main__":
    main()
