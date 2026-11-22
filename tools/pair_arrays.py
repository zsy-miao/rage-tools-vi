#!/usr/bin/env python3
"""Export every 0x8f18aff0 (u32 hash, f32) pair array with root context."""
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
PAIR_TAG = 0x8F18AFF0


def extract_object(cli, archive):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "object.bin"
        subprocess.run(
            [str(cli), "extract-zlib", str(archive), f"{OBJECT_START:x}", f"{OBJECT_END:x}", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        return path.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--tsv", type=Path, default=Path("handoff/script-pair-arrays.tsv"))
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
    roots_by_hash = defaultdict(set)
    values_by_hash = defaultdict(list)
    for index in range(count):
        offset = offsets[index]
        size = end(index) - offset
        if size < 48:
            continue
        header = struct.unpack_from("<12I", data, offset)
        used, stride = header[5], header[6]
        body = size - 48
        if header[10] != PAIR_TAG or stride != 8 or used * stride > body or body - used * stride >= 16:
            continue
        root = root_of(index)
        root_offset = offsets[root]
        root_id, root_flags, root_type = struct.unpack_from("<3I", data, root_offset)
        for i in range(used):
            name_hash, value = struct.unpack_from("<If", data, offset + 48 + i * stride)
            rows.append((
                root, f"0x{root_id:08x}", lookup.get(root_id, ""), f"0x{root_flags >> 16:x}",
                f"0x{root_type:08x}", index, i, f"0x{name_hash:08x}", f"{value:.7g}",
            ))
            roots_by_hash[name_hash].add(root_id)
            values_by_hash[name_hash].append(value)

    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow([
            "root_record", "root_id", "root_name", "root_class", "root_type",
            "array_record", "pair_index", "hash", "value",
        ])
        writer.writerows(rows)

    print(f"pairs: {len(rows)}; arrays: {len({row[5] for row in rows})}; hashes: {len(roots_by_hash)}")
    print("hash\troots\tpairs\tvalue_min\tvalue_max")
    for name_hash, roots in sorted(roots_by_hash.items(), key=lambda item: -len(item[1]))[:20]:
        values = values_by_hash[name_hash]
        print(
            f"0x{name_hash:08x}\t{len(roots)}\t{len(values)}\t"
            f"{min(values):.6g}\t{max(values):.6g}"
        )


if __name__ == "__main__":
    main()
