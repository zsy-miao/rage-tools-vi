#!/usr/bin/env python3
"""Decode the class-0 0x5387a04e bone table and its 0x1ebb416b point arrays."""
import argparse
import csv
from collections import Counter
from pathlib import Path
import struct
import subprocess
import tempfile

OBJECT_START, OBJECT_END = 0x53000, 0xC3B45
TABLE_TAG = 0x5387A04E
BONE_TAG = 0x6503B274
POINT_TAG = 0x1EBB416B
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
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--tsv", type=Path, help="write the flattened bone table here")
    parser.add_argument("--points-tsv", type=Path, help="write one row per point/edge entry here")
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

    def array(index):
        offset = offsets[index]
        size = end(index) - offset
        if size < 48:
            return None
        header = struct.unpack_from("<12I", data, offset)
        used, stride = header[5], header[6]
        body = size - 48
        if not stride or used * stride > body or body - used * stride >= 16:
            return None
        return offset, used, stride, header

    tables = []
    point_arrays = 0
    for index in range(count):
        parsed = array(index)
        if not parsed:
            continue
        offset, used, stride, header = parsed
        if header[10] == TABLE_TAG:
            entries = []
            for i in range(used):
                base = offset + 48 + i * stride
                name_hash, zero, address, tag = struct.unpack_from("<4I", data, base)
                target = by_address.get(address) if tag == 0x71717171 else None
                entries.append((name_hash, target))
            tables.append((index, entries))
        elif header[10] == POINT_TAG:
            point_arrays += 1

    table_hashes = {name for _, entries in tables for name, _ in entries}
    pair_hashes = set()
    for index in range(count):
        parsed = array(index)
        if not parsed:
            continue
        offset, used, stride, header = parsed
        if header[10] == PAIR_TAG:
            for i in range(used):
                pair_hashes.add(struct.unpack_from("<I", data, offset + 48 + i * stride)[0])

    print(f"tables: {len(tables)}; entries: {sum(len(e) for _, e in tables)}; point arrays: {point_arrays}")
    print(f"table hash namespace: {len(table_hashes)}; pair hash namespace: {len(pair_hashes)}; overlap: {len(table_hashes & pair_hashes)}")
    print("table entry counts:", Counter(len(entries) for _, entries in tables).most_common(12))
    target_types = Counter()
    for _, entries in tables:
        for _, target in entries:
            if target is not None:
                target_types[struct.unpack_from("<I", data, offsets[target] + 8)[0]] += 1
    print("target types:", [(hex(tag), total) for tag, total in target_types.most_common()])

    if args.points_tsv:
        args.points_tsv.parent.mkdir(parents=True, exist_ok=True)
        with args.points_tsv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow([
                "root_record", "root_id", "root_class", "table_record", "bone_index",
                "bone_hash", "point_index", "kind", "ax", "ay", "az", "bx", "by", "bz", "id",
            ])
            for table_index, entries in tables:
                root = root_of(table_index)
                root_offset = offsets[root]
                root_id, root_flags, _ = struct.unpack_from("<3I", data, root_offset)
                for bone_index, (name_hash, target) in enumerate(entries):
                    if target is None:
                        continue
                    child = None
                    for position in range(offsets[target], end(target) - 7, 8):
                        address, tag = struct.unpack_from("<II", data, position)
                        if tag == 0x71717171 and address in by_address:
                            child = by_address[address]
                            break
                    if child is None:
                        continue
                    parsed = array(child)
                    if not parsed:
                        continue
                    child_offset, used, stride, _ = parsed
                    for point_index in range(used):
                        base = child_offset + 48 + point_index * stride
                        ax, ay, az = struct.unpack_from("<3f", data, base)
                        bx, by, bz = struct.unpack_from("<3f", data, base + 0x10)
                        ident = struct.unpack_from("<I", data, base + 0x20)[0]
                        a_nonzero = any(abs(v) > 1e-7 for v in (ax, ay, az))
                        b_nonzero = any(abs(v) > 1e-7 for v in (bx, by, bz))
                        kind = "edge" if a_nonzero and b_nonzero else "point" if a_nonzero else "zero"
                        writer.writerow([
                            root, f"0x{root_id:08x}", f"0x{root_flags >> 16:x}", table_index,
                            bone_index, f"0x{name_hash:08x}", point_index, kind,
                            f"{ax:.6g}", f"{ay:.6g}", f"{az:.6g}",
                            f"{bx:.6g}", f"{by:.6g}", f"{bz:.6g}", f"0x{ident:08x}",
                        ])

    if args.tsv:
        args.tsv.parent.mkdir(parents=True, exist_ok=True)
        with args.tsv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow([
                "root_record", "root_id", "root_class", "root_type",
                "table_record", "bone_index", "bone_hash", "bone_record",
                "point_record", "point_count", "first_x", "first_y", "first_z", "first_id",
            ])
            for table_index, entries in tables:
                root = root_of(table_index)
                root_offset = offsets[root]
                root_id, root_flags, root_type = struct.unpack_from("<3I", data, root_offset)
                for bone_index, (name_hash, target) in enumerate(entries):
                    bone_record = target if target is not None else ""
                    point_record = ""
                    point_count = ""
                    first = ("", "", "", "")
                    if target is not None:
                        child = None
                        for position in range(offsets[target], end(target) - 7, 8):
                            address, tag = struct.unpack_from("<II", data, position)
                            if tag == 0x71717171 and address in by_address:
                                child = by_address[address]
                                break
                        if child is not None:
                            parsed = array(child)
                            if parsed:
                                child_offset, used, stride, header = parsed
                                point_record = child
                                point_count = used
                                x, y, z = struct.unpack_from("<3f", data, child_offset + 48)
                                first_id = struct.unpack_from("<I", data, child_offset + 48 + 0x20)[0]
                                first = (f"{x:.6g}", f"{y:.6g}", f"{z:.6g}", f"0x{first_id:08x}")
                    writer.writerow([
                        root, f"0x{root_id:08x}", f"0x{root_flags >> 16:x}", f"0x{root_type:08x}",
                        table_index, bone_index, f"0x{name_hash:08x}", bone_record,
                        point_record, point_count, *first,
                    ])

    print("\ntable samples")
    for table_index, entries in tables[: args.limit]:
        print(f"  table rec {table_index}: {len(entries)} entries")
        for name, target in entries[:5]:
            detail = "-"
            if target is not None:
                target_size = end(target) - offsets[target]
                target_tag = struct.unpack_from("<I", data, offsets[target] + 8)[0]
                child = None
                for position in range(offsets[target], end(target) - 7, 8):
                    address, tag = struct.unpack_from("<II", data, position)
                    if tag == 0x71717171 and address in by_address:
                        child = by_address[address]
                        break
                detail = f"target={target} size={target_size} tag=0x{target_tag:08x}"
                if child is not None:
                    parsed = array(child)
                    if parsed:
                        detail += f" child={child} count={parsed[1]} stride={parsed[2]} type=0x{parsed[3][10]:08x}"
            print(f"    0x{name:08x} {detail}")


if __name__ == "__main__":
    main()
