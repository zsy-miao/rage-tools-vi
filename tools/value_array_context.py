#!/usr/bin/env python3
"""Link typed 48-byte-header value arrays to their nearest named ancestors."""
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
    parser.add_argument("--tag", type=lambda value: int(value, 0), default=0xC92CDECA)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    count = struct.unpack_from("<I", data, 0x14)[0]
    offsets = struct.unpack_from(f"<{count}Q", data, 0x28)
    by_address = {offset + 8: index for index, offset in enumerate(offsets)}

    def end(index):
        return offsets[index + 1] if index + 1 < count else len(data)

    def pointers(index):
        result = []
        for position in range(offsets[index], end(index) - 7, 8):
            address, tag = struct.unpack_from("<II", data, position)
            if tag == 0x71717171 and address in by_address:
                result.append(by_address[address])
        return result

    parent = [None] * count
    for source in range(count):
        for target in pointers(source):
            if parent[target] is None:
                parent[target] = source

    lookup = {}
    for name in candidates(Path("."), True):
        for variant in {name, name.lower()}:
            lookup.setdefault(joaat(variant), set()).add(variant)

    def name_at(index, field):
        if offsets[index] + field + 4 > end(index):
            return None
        value = struct.unpack_from("<I", data, offsets[index] + field)[0]
        labels = lookup.get(value)
        return sorted(labels)[0] if labels else None

    arrays = []
    for index, offset in enumerate(offsets):
        size = end(index) - offset
        if size < 48 or has_pointer(data, offset, size):
            continue
        header = struct.unpack_from("<12I", data, offset)
        used, stride = header[5], header[6]
        body = size - 48
        if not stride or used * stride > body or body - used * stride >= 16:
            continue
        if header[10] == args.tag:
            arrays.append((index, offset, size, used, stride, header))

    named = Counter()
    class_counts = Counter()
    root_ids = Counter()
    rows = []
    for index, offset, size, entries, stride, header in arrays:
        chain = []
        cursor = index
        seen = set()
        for _ in range(16):
            if cursor in seen:
                break
            seen.add(cursor)
            names = [name for name in (name_at(cursor, 0), name_at(cursor, 0x10)) if name]
            chain.append((cursor, end(cursor) - offsets[cursor], names))
            if names:
                break
            cursor = parent[cursor]
            if cursor is None:
                break
        nearest = chain[-1][2] if chain and chain[-1][2] else []
        for name in nearest:
            named[name] += 1
        root = index
        root_seen = set()
        while parent[root] is not None and root not in root_seen:
            root_seen.add(root)
            root = parent[root]
        root_flags = struct.unpack_from("<I", data, offsets[root] + 4)[0]
        root_id = struct.unpack_from("<I", data, offsets[root])[0]
        root_type = (
            struct.unpack_from("<I", data, offsets[root] + 8)[0]
            if end(root) - offsets[root] >= 12
            else 0
        )
        class_counts[root_flags >> 16] += 1
        root_ids[root_id] += 1
        width = min(3, stride // 4)
        first = struct.unpack_from(f"<{width}f", data, offset + 48)
        first = first + (0.0,) * (3 - width)
        rows.append((index, size, entries, stride, first, nearest, chain, root, root_id, root_flags, root_type))

    print(f"tag 0x{args.tag:08x}: {len(arrays)} arrays")
    print(f"named ancestors: {sum(1 for row in rows if row[5])}")
    for name, total in named.most_common(30):
        print(f"  {name}\t{total}")
    print(f"unique roots: {len(root_ids)}")
    print("root classes: " + ", ".join(f"{value:#x}:{total}" for value, total in sorted(class_counts.items())))
    print("\narrays")
    for index, size, entries, stride, first, nearest, chain, root, root_id, root_flags, root_type in rows[: args.limit]:
        chain_text = " > ".join(
            f"{idx}({size}B{'/' + ','.join(names) if names else ''})" for idx, size, names in chain
        )
        print(
            f"  rec {index} size={size} entries={entries} stride={stride} first=({first[0]:.5g},{first[1]:.5g},{first[2]:.5g}) "
            f"root={root}/0x{root_id:08x}/class={root_flags >> 16:#x}/type=0x{root_type:08x} "
            f"names={nearest or '-'} chain={chain_text}"
        )


if __name__ == "__main__":
    main()
