"""The game's own name hash, as read out of the executable.

`FUN_145305880` hashes an asset name for archive lookup. Its structure is Murmur3
x64-128 with three details that no corpus study could have guessed:

* every byte is first mapped through a 256-byte table at `0x1465b23b0`, which turns
  out to be `tolower()` plus `'\\' -> '/'` (exactly 27 non-identity entries);
* the result is compared against a stored 64-bit value at `obj+0x70`;
* the 16-bit id the archive actually indexes by is then looked *up* — it is assigned
  from a runtime table, not derived from the hash bits.

So a name's 32-bit JOAAT is irrelevant here, and the 16-bit id cannot be computed
offline. What *can* be computed is the 64-bit hash, which is what this tool does.

    python3 tools/name_hash_game.py --hash "vehicles/car.wft"
    python3 tools/name_hash_game.py --probe /path/to/*.rpf
"""

import argparse
import csv
import struct
import sys
from pathlib import Path

M64 = (1 << 64) - 1
C1 = 0x87C37B91114253D5
C2 = 0x4CF5AD432745937F


def rotl(value, count):
    return ((value << count) | (value >> (64 - count))) & M64


def fmix(value):
    value ^= value >> 33
    value = (value * 0xFF51AFD7ED558CCD) & M64
    value ^= value >> 33
    value = (value * 0xC4CEB9FE1A85EC53) & M64
    value ^= value >> 33
    return value


def substitute(data):
    """The executable's 256-byte map: tolower() with '\\\\' folded to '/'."""
    out = bytearray(len(data))
    for index, byte in enumerate(data):
        if 0x41 <= byte <= 0x5A:
            byte += 0x20
        elif byte == 0x5C:      # '\\' -> '/', the only non-case change in the table
            byte = 0x2F
        out[index] = byte
    return bytes(out)


def murmur3_x64_128(data, seed=0):
    h1 = h2 = seed
    length = len(data)
    blocks = length // 16
    for index in range(blocks):
        k1 = int.from_bytes(data[16 * index:16 * index + 8], "little")
        k2 = int.from_bytes(data[16 * index + 8:16 * index + 16], "little")
        k1 = (k1 * C1) & M64
        k1 = rotl(k1, 31)
        k1 = (k1 * C2) & M64
        h1 ^= k1
        h1 = rotl(h1, 27)
        h1 = (h1 + h2) & M64
        h1 = (h1 * 5 + 0x52DCE729) & M64
        k2 = (k2 * C2) & M64
        k2 = rotl(k2, 33)
        k2 = (k2 * C1) & M64
        h2 ^= k2
        h2 = rotl(h2, 31)
        h2 = (h2 + h1) & M64
        h2 = (h2 * 5 + 0x38495AB5) & M64
    tail = data[16 * blocks:]
    k1 = k2 = 0
    for index, byte in enumerate(tail):
        if index < 8:
            k1 |= byte << (8 * index)
        else:
            k2 |= byte << (8 * (index - 8))
    if tail:
        if len(tail) > 8:
            k2 = (k2 * C2) & M64
            k2 = rotl(k2, 33)
            k2 = (k2 * C1) & M64
            h2 ^= k2
        k1 = (k1 * C1) & M64
        k1 = rotl(k1, 31)
        k1 = (k1 * C2) & M64
        h1 ^= k1
    h1 ^= length
    h2 ^= length
    h1 = (h1 + h2) & M64
    h2 = (h2 + h1) & M64
    h1 = fmix(h1)
    h2 = fmix(h2)
    h1 = (h1 + h2) & M64
    h2 = (h2 + h1) & M64
    return h1, h2


def name_forms(name):
    base = name.replace("\\", "/").lower()
    forms = {base}
    leaf = base.rsplit("/", 1)[-1]
    if "." in leaf:
        forms.add(base.rsplit(".", 1)[0])
        forms.add(leaf.rsplit(".", 1)[0])
    forms.add(leaf)
    return forms


def probe(paths, names_path):
    names = [row["name"] for row in csv.DictReader(names_path.open(), delimiter="\t")
             if row.get("name")]
    words = set()
    headers = 0
    for path in paths:
        size = path.stat().st_size
        with path.open("rb") as handle:
            for offset in range(0, max(0, size - 0x60), 0x4000):
                handle.seek(offset)
                header = handle.read(0x60)
                if len(header) < 0x60 or header[:4] != b"9FPR":
                    continue
                front_end, block = struct.unpack_from("<II", header, 4)
                if not (0x60 < block <= front_end <= size - offset):
                    continue
                handle.seek(offset + 0x10)
                region = handle.read(front_end - 0x10)
                for index in range(0, len(region) - 7, 8):
                    words.add(struct.unpack_from("<Q", region, index)[0])
                headers += 1
    print(f"headers {headers}  distinct front-region u64 {len(words):,}")
    hits = 0
    candidates = 0
    for name in names:
        for form in name_forms(name):
            candidates += 1
            first, second = murmur3_x64_128(substitute(form.encode()))
            if first in words or second in words:
                hits += 1
                print(f"  HIT {name} ({form}) {first:#018x} {second:#018x}")
    print(f"candidates {candidates:,}  hits {hits}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--hash", nargs="+", help="names to hash")
    parser.add_argument("--probe", nargs="+", type=Path,
                        help="archives whose front regions to search")
    parser.add_argument("--names", type=Path, default=Path("handoff/names.tsv"))
    args = parser.parse_args()

    if args.hash:
        for name in args.hash:
            first, second = murmur3_x64_128(substitute(name.encode()))
            print(f"{name}\n  {first:#018x} {second:#018x}")
        return 0
    if args.probe:
        return probe(args.probe, args.names)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
