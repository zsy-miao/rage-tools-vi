#!/usr/bin/env python3
"""Validate 48-byte array headers and classify their 16-byte value entries."""
import argparse
from collections import Counter, defaultdict
import math
from pathlib import Path
import struct
import subprocess
import tempfile

OBJECT_START, OBJECT_END = 0x53000, 0xC3B45


def extract_object(cli, archive):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "object.bin"
        subprocess.run(
            [str(cli), "extract-zlib", str(archive), f"{OBJECT_START:x}", f"{OBJECT_END:x}", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        return path.read_bytes()


def has_pointer(data, offset, size):
    for position in range(offset, offset + size - 7, 8):
        if struct.unpack_from("<I", data, position + 4)[0] == 0x71717171:
            return True
    return False


def classify(entry):
    floats = struct.unpack("<4f", entry)
    words = struct.unpack("<4I", entry)
    finite = [math.isfinite(value) and abs(value) < 1_000_000 for value in floats]
    if words[1] == 0 and words[3] == 0 and finite[0] and finite[2]:
        return "vec2_f0_f2"
    if words[3] == 0 and all(finite[:3]):
        return "vec3_f0_f1_f2"
    if all(finite):
        return "vec4"
    if all(word == 0 or word < 0x10000 for word in words):
        return "small_ints"
    return "other"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--tag", type=lambda value: int(value, 0), default=None)
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    count = struct.unpack_from("<I", data, 0x14)[0]
    offsets = struct.unpack_from(f"<{count}Q", data, 0x28)
    candidates = []
    for index, offset in enumerate(offsets):
        end = offsets[index + 1] if index + 1 < count else len(data)
        size = end - offset
        if size < 48 or (size - 48) % 16 or has_pointer(data, offset, size):
            continue
        header = struct.unpack_from("<12I", data, offset)
        entries = (size - 48) // 16
        shapes = Counter(classify(data[offset + 48 + 16 * i : offset + 64 + 16 * i]) for i in range(entries))
        candidates.append((index, offset, size, entries, header, shapes))

    count_ok = [item for item in candidates if item[4][5] == item[3]]
    stride_ok = [item for item in candidates if item[4][6] == 16]
    both = [item for item in candidates if item[4][5] == item[3] and item[4][6] == 16]
    print(f"no-pointer header-48 arrays: {len(candidates)}")
    print(f"  +0x14 count == entries: {len(count_ok)}")
    print(f"  +0x18 stride == 16:     {len(stride_ok)}")
    print(f"  both:                   {len(both)}")

    print("\ntag +0x28 distribution (both-valid arrays)")
    for tag, total in Counter(item[4][10] for item in both).most_common(20):
        print(f"  0x{tag:08x}\t{total}")

    print("\nentry shape per array (both-valid arrays)")
    for shape, total in Counter(
        "mixed" if len(item[5]) > 1 else next(iter(item[5])) for item in both
    ).most_common(20):
        print(f"  {shape:16} {total}")

    selected = [item for item in both if args.tag is None or item[4][10] == args.tag]
    print(f"\nexamples tag={args.tag if args.tag is not None else 'any'} ({len(selected)})")
    for index, offset, size, entries, header, shapes in selected[: args.limit]:
        print(
            f"  record {index} off=0x{offset:x} size={size} entries={entries} "
            f"hdr=[{header[4]},{header[5]},{header[6]},{header[7]:#x},{header[10]:#x}] "
            f"shape={dict(shapes)}"
        )
        for i in range(min(entries, 4)):
            entry = data[offset + 48 + 16 * i : offset + 64 + 16 * i]
            print(f"    [{i}] {entry.hex()} f={['%.5g' % v for v in struct.unpack('<4f', entry)]}")


if __name__ == "__main__":
    main()
