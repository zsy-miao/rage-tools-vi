#!/usr/bin/env python3
"""Decode array headers with count, stride, and element type hash."""
import argparse
from collections import Counter, defaultdict
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from root_names import candidates, joaat  # noqa: E402

OBJECT_START, OBJECT_END = 0x53000, 0xC3B45
TYPES = {"vector2", "vector3", "vector4", "vec2", "vec3", "vec4", "float2", "float3", "float4"}


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


def entry_kind(data, offset, stride):
    if stride % 4:
        return "raw"
    words = struct.unpack_from(f"<{stride // 4}I", data, offset)
    floats = struct.unpack_from(f"<{stride // 4}f", data, offset)
    if all(word == 0 for word in words):
        return "zero"
    if stride == 8:
        if words[1] and math.isfinite(floats[1]) and abs(floats[1]) < 1_000_000:
            if not (math.isfinite(floats[0]) and abs(floats[0]) < 1_000_000):
                return "id+f32"
        if all(math.isfinite(value) and abs(value) < 1_000_000 for value in floats):
            return "f32x2"
    if stride == 16 and words[3] == 0 and all(
        math.isfinite(value) and abs(value) < 1_000_000 for value in floats[:3]
    ):
        return "vec3+pad"
    if stride == 48 and all(word == 0 for word in words[3:8]) and all(
        word == 0 for word in words[9:12]
    ):
        if all(math.isfinite(value) and abs(value) < 1_000_000 for value in floats[:3]):
            return "vec3+pad+id"
        if all(word == 0 for word in words[:4]) and all(
            math.isfinite(value) and abs(value) < 1_000_000 for value in floats[4:7]
        ):
            return "pad+vec3+id"
    if all(math.isfinite(value) and abs(value) < 1_000_000 for value in floats):
        return f"f32x{stride // 4}"
    if all(word < 0x10000 for word in words):
        return f"intx{stride // 4}"
    return "mixed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--tag", type=lambda value: int(value, 0), default=None)
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    count = struct.unpack_from("<I", data, 0x14)[0]
    offsets = struct.unpack_from(f"<{count}Q", data, 0x28)

    lookup = {}
    for name in set(TYPES) | candidates(Path("."), True):
        lookup.setdefault(joaat(name), name)

    groups = defaultdict(list)
    rejected = Counter()
    for index, offset in enumerate(offsets):
        end = offsets[index + 1] if index + 1 < count else len(data)
        size = end - offset
        if size < 48 or has_pointer(data, offset, size):
            continue
        header = struct.unpack_from("<12I", data, offset)
        used, stride, tag = header[5], header[6], header[10]
        body = size - 48
        if not stride or (used and stride > body):
            rejected["stride"] += 1
            continue
        if used * stride > body or body - used * stride >= 16:
            rejected["count"] += 1
            continue
        if used > 1024:
            rejected["large"] += 1
            continue
        kinds = Counter(entry_kind(data, offset + 48 + i * stride, stride) for i in range(used))
        groups[(tag, stride)].append((index, offset, size, used, header, kinds))

    print(f"valid arrays: {sum(len(value) for value in groups.values())}")
    print(f"rejected: {dict(rejected)}")
    print("\ntag/stride groups")
    for (tag, stride), rows in sorted(groups.items(), key=lambda item: -len(item[1]))[: args.limit]:
        name = lookup.get(tag, "?")
        counts = Counter(row[3] for row in rows)
        shapes = Counter()
        for row in rows:
            shapes.update(row[5])
        top_counts = ", ".join(f"{value}:{total}" for value, total in counts.most_common(5))
        top_shapes = ", ".join(f"{value}:{total}" for value, total in shapes.most_common(5))
        print(
            f"  0x{tag:08x} {name:8} stride={stride:2} arrays={len(rows):4} "
            f"counts=[{top_counts}] entries=[{top_shapes}]"
        )

    selected = [
        row
        for (tag, stride), rows in groups.items()
        if args.tag is None or tag == args.tag
        for row in rows
    ]
    print(f"\nexamples tag={args.tag if args.tag is not None else 'first'}")
    for index, offset, size, used, header, kinds in selected[: args.limit]:
        print(
            f"  rec {index} off=0x{offset:x} size={size} count={used} stride={header[6]} "
            f"tag=0x{header[10]:08x}/{lookup.get(header[10], '?')} kinds={dict(kinds)}"
        )


if __name__ == "__main__":
    main()
