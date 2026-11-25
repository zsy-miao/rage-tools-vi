#!/usr/bin/env python3
"""Join vehicle curve keys to same-root named parts and rotation leaves."""
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
CURVE_TAG = 0xB066759F
ROTATION_TAG = 0xFC86DDE2
KEY_NODE_TAG = 0xD2AFC0B6
VEHICLE_ROOT_TYPE = 0xC48AB516


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
    parser.add_argument("--curves", type=Path, default=Path("handoff/script-vehicle-curves.tsv"))
    parser.add_argument("--bones", type=Path, default=Path("tools/vehicle_bone_names.txt"))
    parser.add_argument("--tsv", type=Path, default=Path("handoff/script-vehicle-curve-join.tsv"))
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    count = struct.unpack_from("<I", data, 0x14)[0]
    offsets = struct.unpack_from(f"<{count}Q", data, 0x28)
    by_address = {offset + 8: index for index, offset in enumerate(offsets)}

    def end(index):
        return offsets[index + 1] if index + 1 < count else len(data)

    children = [[] for _ in range(count)]
    for source in range(count):
        for position in range(offsets[source], end(source) - 7, 8):
            address, tag = struct.unpack_from("<II", data, position)
            target = by_address.get(address) if tag == 0x71717171 else None
            if target is not None:
                children[source].append(target)

    lookup = {}
    for name in candidates(Path("."), True):
        for variant in {name, name.lower()}:
            lookup.setdefault(joaat(variant), variant)
    known_names = set()
    for name in args.bones.read_text(errors="ignore").splitlines():
        name = name.strip()
        if name:
            known_names.add(name)
            known_names.add(name.lower())
            for suffix in ("_mover", "_dummy", "_rot"):
                known_names.add(name + suffix)
                known_names.add(name.lower() + suffix)
    key_name = {}
    for name in known_names:
        key_name.setdefault(joaat(name), name)

    curves = defaultdict(list)
    with args.curves.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            curves[row["root_id"]].append(row)

    root_by_id = {}
    for index, offset in enumerate(offsets):
        size = end(index) - offset
        if size >= 12 and struct.unpack_from("<I", data, offset + 8)[0] == VEHICLE_ROOT_TYPE:
            root_by_id[f"0x{struct.unpack_from('<I', data, offset)[0]:08x}"] = index

    def subtree(index):
        seen = set()
        stack = [index]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(children[node])
        return seen

    rows = []
    channel_stats = defaultdict(lambda: {"curves": 0, "roots": 0, "name_hits": 0, "part_hits": 0})
    for root_id, entries in curves.items():
        root = root_by_id.get(root_id)
        if root is None:
            continue
        nodes = subtree(root)
        name_hashes = set()
        named_parts = set()
        rotations = 0
        for node in nodes:
            offset = offsets[node]
            size = end(node) - offset
            node_type = 0
            if size >= 12:
                node_type = struct.unpack_from("<I", data, offset + 8)[0]
                if node_type == ROTATION_TAG:
                    rotations += 1
            if node_type != KEY_NODE_TAG:
                if size >= 4:
                    name_hashes.add(struct.unpack_from("<I", data, offset)[0])
                if size >= 20:
                    name_hashes.add(struct.unpack_from("<I", data, offset + 0x10)[0])
            for field in (0, 0x10):
                if size >= field + 4:
                    value = struct.unpack_from("<I", data, offset + field)[0]
                    if value in lookup:
                        named_parts.add(lookup[value])
        for row in entries:
            key = row["key_hash"]
            value = int(key, 16)
            name = key_name.get(value, row["key_name"])
            same_root_name = value in name_hashes
            base_name = name[:-6] if name.endswith("_mover") else name
            part_present = bool(base_name and base_name in named_parts)
            stats = channel_stats[key]
            stats["curves"] += 1
            stats["roots"] += 1
            stats["name_hits"] += int(same_root_name)
            stats["part_hits"] += int(part_present)
            rows.append((root_id, row["root_name"], key, name, len(nodes), rotations, same_root_name, part_present))

    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow([
            "root_id", "root_name", "key_hash", "key_name", "subtree_records",
            "rotation_leaves", "same_root_name_hash", "named_part_present",
        ])
        writer.writerows(rows)

    print("key\tname\tcurves\troots\tname_hash_hits\tpart_hits")
    for key, stats in sorted(channel_stats.items(), key=lambda item: -item[1]["curves"]):
        print(
            f"{key}\t{key_name.get(int(key, 16), '-')}\t{stats['curves']}\t"
            f"{stats['roots']}\t{stats['name_hits']}\t{stats['part_hits']}"
        )


if __name__ == "__main__":
    main()
