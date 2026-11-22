"""Search RPF front-region words for any hash of any known name.

Why: the front regions are uniform random under every entry interpretation we
tried, and the loader shows no decryption.  If the front region is a *hash
table* that is simply stored as-is, then some 4-byte word in it must equal the
project hash of a name we already know (36,952 names).

This walks every known name through several hash functions and several path
normalizations, then tests the resulting values against every 4-byte-aligned
word in Front A and Front B of every archive.

A hit is only interesting if it is rare: the expected number of collisions by
chance is printed so a single accidental match is not over-read.

  python3 tools/front_hash_probe.py --source /home/lynxnathan/gta6-source
"""

import argparse
import struct
import sys
from pathlib import Path

MAGIC = b"9FPR"


def joaat(data, seed=0):
    value = seed & 0xFFFFFFFF
    for byte in data:
        value = (value + byte) & 0xFFFFFFFF
        value = (value + (value << 10)) & 0xFFFFFFFF
        value ^= value >> 6
    value = (value + (value << 3)) & 0xFFFFFFFF
    value ^= value >> 11
    value = (value + (value << 15)) & 0xFFFFFFFF
    return value & 0xFFFFFFFF


def fnv1a(data):
    value = 0x811C9DC5
    for byte in data:
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


def fnv1(data):
    value = 0x811C9DC5
    for byte in data:
        value = ((value * 0x01000193) & 0xFFFFFFFF) ^ byte
    return value


def djb2(data):
    value = 5381
    for byte in data:
        value = ((value * 33) + byte) & 0xFFFFFFFF
    return value


def djb2_xor(data):
    value = 5381
    for byte in data:
        value = ((value * 33) ^ byte) & 0xFFFFFFFF
    return value


def sdbm(data):
    value = 0
    for byte in data:
        value = (byte + (value << 6) + (value << 16) - value) & 0xFFFFFFFF
    return value


def crc32(data):
    import zlib
    return zlib.crc32(data) & 0xFFFFFFFF


ALGOS = {
    "joaat": joaat,
    "fnv1a": fnv1a,
    "fnv1": fnv1,
    "djb2": djb2,
    "djb2x": djb2_xor,
    "sdbm": sdbm,
    "crc32": crc32,
}

SEPARATORS = ("/", "\\")


def name_forms(name):
    """Every normalization a path hash could plausibly be taken over."""
    forms = set()
    base = name.replace("\\", "/")
    lower = base.lower()
    forms.update({base, lower, base.upper()})
    leaf = lower.rsplit("/", 1)[-1]
    forms.add(leaf)
    if "." in leaf:
        stem = leaf.rsplit(".", 1)[0]
        forms.add(stem)
        forms.add(stem.replace("/", "\\"))
    for sep in SEPARATORS:
        forms.add(lower.replace("/", sep))
        forms.add(lower.lstrip("/").replace("/", sep))
    for prefix in ("common:/", "platform:/", "data/", "/", "./"):
        forms.add(prefix + lower)
    # the loader may hash with a trailing NUL included
    return [f for f in forms if f]


def load_names(path):
    names = []
    with path.open() as handle:
        header = handle.readline()
        if not header.startswith("hash"):
            handle.seek(0)
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[1]:
                names.append(parts[1])
    return names


def archive_headers(source, limit):
    """Yield (path, offset) for every 9FPR header, like front_b_modes.py."""
    found = []
    for path in sorted(source.glob("*.rpf")):
        size = path.stat().st_size
        with path.open("rb") as handle:
            for offset in range(0, max(0, size - 0x60), 0x4000):
                handle.seek(offset)
                header = handle.read(0x60)
                if len(header) < 0x60 or header[:4] != MAGIC:
                    continue
                front_end = struct.unpack_from("<I", header, 4)[0]
                block = struct.unpack_from("<I", header, 8)[0]
                if not (0x60 <= block <= front_end <= size - offset):
                    continue
                found.append((path, offset, block, front_end))
                if limit and len(found) >= limit:
                    return found
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("."))
    parser.add_argument("--names", type=Path, default=Path("handoff/names.tsv"))
    parser.add_argument("--limit", type=int, default=0, help="max headers scanned")
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--max-hits", type=int, default=40)
    args = parser.parse_args()

    names = load_names(args.names)
    print(f"names: {len(names)}", file=sys.stderr)

    headers = archive_headers(args.source, args.limit)
    print(f"headers: {len(headers)}", file=sys.stderr)

    words = {}
    total_words = 0
    for path, offset, block, front_end in headers:
        with path.open("rb") as handle:
            handle.seek(offset + 0x10)
            front_a = handle.read(block - 0x10)
            front_b = handle.read(front_end - block)
        for region, blob in (("A", front_a), ("B", front_b)):
            for i in range(0, len(blob) - 3, args.stride):
                value = struct.unpack_from("<I", blob, i)[0]
                words.setdefault(value, []).append((path.name, offset, region, i))
                total_words += 1

    print(f"front words ({args.stride}-aligned): {total_words}, distinct: {len(words)}",
          file=sys.stderr)

    hits = []
    for name in names:
        forms = name_forms(name)
        for form in forms:
            for tag, fn in ALGOS.items():
                for data in (form.encode("utf-8", "ignore"),
                             form.encode("utf-8", "ignore") + b"\0"):
                    value = fn(data)
                    if value in words:
                        for path, offset, region, index in words[value]:
                            hits.append((name, form, tag, value, path, offset, region, index))

    print(f"\nexpected chance collisions: {len(names) * 20 * len(ALGOS) * 2 * len(words) / 2**32:.2f}")
    print(f"hits: {len(hits)}")
    for name, form, tag, value, path, offset, region, index in hits[: args.max_hits]:
        print(f"  {tag:6s} 0x{value:08x}  {path}+0x{offset:x} front{region}+0x{index:x}  {form}")


if __name__ == "__main__":
    main()
