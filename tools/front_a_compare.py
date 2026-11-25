"""Compare the post-signature Front A tables across the RPF9 controls."""

import argparse
from collections import Counter
import math
from pathlib import Path
import struct

SCOPES = (
    ("story", "story000_bvh4.rpf", 0),
    ("core_root", "core_licenses_data.rpf", 0),
    ("core_emb", "core_licenses_data.rpf", 0x1000),
    ("script_root", "script.rpf", 0),
    ("script_small", "script.rpf", 0x1000),
    ("appdata0", "appdata0.rpf", 0),
)


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
    parser.add_argument("archive_dir", type=Path, nargs="?", default=Path("."))
    args = parser.parse_args()

    tables = {}
    for name, filename, base in SCOPES:
        data = (args.archive_dir / filename).read_bytes()
        block = struct.unpack_from("<I", data, base + 8)[0]
        front_a = data[base + 0x60 : base + block]
        signature = front_a[:0x100]
        table = front_a[0x100:]
        tables[name] = table
        print(
            f"{name}: frontA {len(front_a)}, signature256 entropy {entropy(signature):.4f}, "
            f"table {len(table)} entropy {entropy(table):.4f}, first16 {table[:16].hex()}"
        )

    print("\npairwise table shared prefixes")
    names = list(tables)
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            left, right = tables[first], tables[second]
            length = min(len(left), len(right))
            prefix = next(
                (offset for offset in range(length) if left[offset] != right[offset]),
                length,
            )
            print(f"  {first} vs {second}: shared {prefix} bytes (mod16={prefix % 16})")

    blocks = Counter()
    for table in tables.values():
        for offset in range(0, len(table) // 16 * 16, 16):
            blocks[table[offset : offset + 16]] += 1
    repeated = {value: count for value, count in blocks.items() if count > 1}
    print(f"\n16-byte table blocks: {sum(blocks.values())}, unique {len(blocks)}, repeated {len(repeated)}")
    for value, count in sorted(repeated.items(), key=lambda item: -item[1])[:10]:
        print(f"  {count} {value.hex()}")


if __name__ == "__main__":
    main()
