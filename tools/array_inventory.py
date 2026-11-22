#!/usr/bin/env python3
"""Export every valid typed array with its root context."""
import argparse
import csv
from collections import Counter, defaultdict
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


def shape(data, offset, stride):
    if stride % 4 or stride > 48:
        return "raw"
    words = struct.unpack_from(f"<{stride // 4}I", data, offset)
    floats = struct.unpack_from(f"<{stride // 4}f", data, offset)
    nonzero = [i for i, word in enumerate(words) if word]
    if not nonzero:
        return "zero"
    if all(word < 0x10000 for word in words):
        return "small_ints"
    if len(nonzero) <= 4 and all(abs(v) < 1_000_000 for v in floats):
        return "few_floats"
    return "mixed"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--tsv", type=Path, default=Path("handoff/script-array-inventory.tsv"))
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    count = struct.unpack_from("<I", data, 0x14)[0]
    offsets = struct.unpack_from(f"<{count}Q", data, 0x28)
    by_address = {offset + 8: index for index, offset in enumerate(offsets)}

    def end(index):
        return offsets[index + 1] if index + 1 < count else len(data)

    parent = [None] * count
    for source in range(count):
        for position in range(offsets[source], end(source) - 7, 8):
            address, tag = struct.unpack_from("<II", data, position)
            target = by_address.get(address) if tag == 0x71717171 else None
            if target is not None and parent[target] is None:
                parent[target] = source

    def root_of(index):
        seen = set()
        while parent[index] is not None and index not in seen:
            seen.add(index)
            index = parent[index]
        return index

    lookup = {}
    for name in candidates(Path("."), True):
        for variant in {name, name.lower()}:
            lookup.setdefault(joaat(variant), variant)

    rows = []
    for index, offset in enumerate(offsets):
        size = end(index) - offset
        if size < 48 or has_pointer(data, offset, size):
            continue
        header = struct.unpack_from("<12I", data, offset)
        used, stride = header[5], header[6]
        body = size - 48
        if not stride or used * stride > body or body - used * stride >= 16:
            continue
        root = root_of(index)
        root_offset = offsets[root]
        root_id, root_flags, root_type = struct.unpack_from("<3I", data, root_offset)
        sample = [shape(data, offset + 48 + i * stride, stride) for i in range(min(used, 4))]
        rows.append((
            root, f"0x{root_id:08x}", lookup.get(root_id, ""), f"0x{root_flags >> 16:x}",
            f"0x{root_type:08x}", index, f"0x{header[10]:08x}", stride, used,
            "/".join(sorted(set(sample))) if sample else "empty",
        ))

    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow([
            "root_record", "root_id", "root_name", "root_class", "root_type",
            "array_record", "type_tag", "stride", "count", "entry_shape",
        ])
        writer.writerows(rows)

    print(f"arrays: {len(rows)}; roots: {len({row[0] for row in rows})}")
    print("type_tag\tstride\tarrays\troots")
    tags = Counter((row[6], row[7]) for row in rows)
    roots_by_tag = defaultdict(set)
    for row in rows:
        roots_by_tag[(row[6], row[7])].add(row[0])
    for (tag, stride), total in tags.most_common(15):
        print(f"{tag}\t{stride}\t{total}\t{len(roots_by_tag[(tag, stride)])}")


if __name__ == "__main__":
    main()
