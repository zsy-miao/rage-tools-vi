#!/usr/bin/env python3
"""Match array header type tags to JOAAT names of likely value types."""
import argparse
from collections import Counter
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from root_names import candidates, joaat  # noqa: E402

OBJECT_START, OBJECT_END = 0x53000, 0xC3B45
TYPES = {
    "vector2", "vector3", "vector4", "vec2", "vec3", "vec4",
    "float2", "float3", "float4", "matrix33", "matrix34", "matrix44",
    "quaternion", "float", "double", "int", "uint", "short", "ushort",
    "byte", "char", "bool", "string", "hash", "joaat", "object", "array",
    "pointer", "struct", "colour", "color", "vector", "point", "bounds",
    "transform", "matrix", "rage__Vector3", "Vector3", "Vector2", "Vector4",
}


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    count = struct.unpack_from("<I", data, 0x14)[0]
    offsets = struct.unpack_from(f"<{count}Q", data, 0x28)

    names = set(TYPES)
    for name in candidates(Path("."), True):
        names.add(name)
        names.add(name.lower())
    lookup = {}
    for name in names:
        lookup.setdefault(joaat(name), name)

    rows = []
    for index, offset in enumerate(offsets):
        end = offsets[index + 1] if index + 1 < count else len(data)
        size = end - offset
        if size < 48 or has_pointer(data, offset, size):
            continue
        header = struct.unpack_from("<12I", data, offset)
        entries = (size - 48) // 16
        rows.append((index, offset, size, entries, header))

    tags = Counter()
    for _, _, _, entries, header in rows:
        if header[5] == entries:
            tags[header[10]] += 1
    named = [(tag, total, lookup.get(tag)) for tag, total in tags.items() if tag in lookup]
    named.sort(key=lambda item: (-item[1], item[2]))
    print(f"header +0x28 tags on count-valid arrays: {len(tags)} distinct")
    for tag, total, name in named[: args.limit]:
        print(f"  0x{tag:08x}\t{total:6}\t{name}")
    print("\ntop unmatched")
    for tag, total in tags.most_common(args.limit):
        if tag not in lookup:
            print(f"  0x{tag:08x}\t{total:6}")

    if named:
        print("\nnamed tag examples")
        for tag, total, name in named[: args.limit]:
            examples = [row for row in rows if row[4][5] == row[3] and row[4][10] == tag][:3]
            for index, offset, size, entries, header in examples:
                print(
                    f"  0x{tag:08x} {name} rec={index} size={size} entries={entries} "
                    f"stride={header[6]} hdr={[header[4],header[5],header[6],header[7],header[9]]}"
                )


if __name__ == "__main__":
    main()
