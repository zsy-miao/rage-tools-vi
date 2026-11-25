#!/usr/bin/env python3
"""Decode 0xb066759f vehicle mover curves and name their JOAAT channels."""
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
KEY_NODE_TAG = 0xD2AFC0B6


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
    parser.add_argument("--tsv", type=Path, default=Path("handoff/script-vehicle-curves.tsv"))
    parser.add_argument("--points-tsv", type=Path, default=Path("handoff/script-vehicle-curve-points.tsv"))
    parser.add_argument("--bones", type=Path, default=Path("tools/vehicle_bone_names.txt"))
    parser.add_argument("--limit", type=int, default=20)
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

    lookup = {}
    for name in candidates(Path("."), True):
        for variant in {name, name.lower()}:
            lookup.setdefault(joaat(variant), variant)
    bone_names = set()
    for name in args.bones.read_text(errors="ignore").splitlines():
        name = name.strip()
        if name:
            bone_names.add(name)
            bone_names.add(name.lower())
            for suffix in ("_mover", "_dummy", "_rot"):
                bone_names.add(name + suffix)
                bone_names.add(name.lower() + suffix)
    for name in bone_names:
        lookup.setdefault(joaat(name), name)

    curves = []
    for index in range(count):
        offset = offsets[index]
        size = end(index) - offset
        if size < 48:
            continue
        header = struct.unpack_from("<12I", data, offset)
        used, stride = header[5], header[6]
        body = size - 48
        if header[10] != CURVE_TAG or stride != 32 or used * stride > body or body - used * stride >= 16:
            continue
        key = None
        cursor = index
        seen = set()
        for _ in range(12):
            if cursor in seen:
                break
            seen.add(cursor)
            if end(cursor) - offsets[cursor] >= 20:
                node_type = struct.unpack_from("<I", data, offsets[cursor] + 8)[0]
                if node_type == KEY_NODE_TAG:
                    key = struct.unpack_from("<I", data, offsets[cursor] + 0x10)[0]
                    break
            if parent[cursor] is None:
                break
            cursor = parent[cursor]
        root = index
        seen = set()
        while parent[root] is not None and root not in seen:
            seen.add(root)
            root = parent[root]
        root_id = struct.unpack_from("<I", data, offsets[root])[0]
        root_name = lookup.get(root_id, "")
        points = []
        for i in range(used):
            values = struct.unpack_from("<8f", data, offset + 48 + i * stride)
            points.append(values)
        if not points:
            continue
        curves.append((index, root_id, root_name, key, points))

    by_key = defaultdict(list)
    for curve in curves:
        by_key[curve[3]].append(curve)

    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow([
            "root_id", "root_name", "array_record", "key_hash", "key_name",
            "points", "t_min", "t_max", "y_min", "y_max", "z_min", "z_max",
        ])
        for index, root_id, root_name, key, points in curves:
            key_name = lookup.get(key, "") if key is not None else ""
            ts = [p[0] for p in points]
            ys = [p[5] for p in points]
            zs = [p[6] for p in points]
            writer.writerow([
                f"0x{root_id:08x}", root_name, index,
                f"0x{key:08x}" if key is not None else "", key_name,
                len(points), f"{min(ts):.6g}", f"{max(ts):.6g}",
                f"{min(ys):.6g}", f"{max(ys):.6g}",
                f"{min(zs):.6g}", f"{max(zs):.6g}",
            ])

    if args.points_tsv:
        args.points_tsv.parent.mkdir(parents=True, exist_ok=True)
        with args.points_tsv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow([
                "root_id", "root_name", "array_record", "key_hash", "key_name",
                "point_index", "t", "x", "y", "z",
            ])
            for index, root_id, root_name, key, points in curves:
                key_name = lookup.get(key, "") if key is not None else ""
                for point_index, values in enumerate(points):
                    writer.writerow([
                        f"0x{root_id:08x}", root_name, index,
                        f"0x{key:08x}" if key is not None else "", key_name,
                        point_index, f"{values[0]:.6g}", f"{values[4]:.6g}",
                        f"{values[5]:.6g}", f"{values[6]:.6g}",
                    ])

    print(f"curves: {len(curves)}; roots: {len({c[1] for c in curves})}; channels: {len(by_key)}")
    print("key_hash\tname\tcurves\troots")
    for key, group in sorted(by_key.items(), key=lambda item: -len(item[1]))[: args.limit]:
        name = lookup.get(key, "")
        print(f"0x{key:08x}\t{name or '-'}\t{len(group)}\t{len({c[1] for c in group})}")


if __name__ == "__main__":
    main()
