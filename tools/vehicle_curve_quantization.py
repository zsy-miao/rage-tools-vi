#!/usr/bin/env python3
"""Native-precision test for degree quantization and leaf-angle identity."""
import argparse
import csv
import math
import random
from collections import defaultdict
from pathlib import Path
import struct
import subprocess
import tempfile

OBJECT_START, OBJECT_END = 0x53000, 0xC3B45
CURVE_TAG = 0xB066759F
KEY_NODE_TAG = 0xD2AFC0B6
ROTATION_TAG = 0xFC86DDE2
VEHICLE_ROOT_TYPE = 0xC48AB516
GRIDS = (1.0, 0.5, 0.25)
THRESHOLD = 0.05


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
    parser.add_argument("--tsv", type=Path, default=Path("handoff/script-vehicle-curve-quantization.tsv"))
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--permutations", type=int, default=100)
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

    parent = [None] * count
    for source in range(count):
        for target in children[source]:
            if parent[target] is None:
                parent[target] = source

    def root_of(index):
        seen = set()
        while parent[index] is not None and index not in seen:
            seen.add(index)
            index = parent[index]
        return index

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

    roots = {}
    for index, offset in enumerate(offsets):
        size = end(index) - offset
        if size >= 12 and struct.unpack_from("<I", data, offset + 8)[0] == VEHICLE_ROOT_TYPE:
            roots[f"0x{struct.unpack_from('<I', data, offset)[0]:08x}"] = index

    leaf_angles = {}
    for root_id, root in roots.items():
        angles = []
        for node in subtree(root):
            offset = offsets[node]
            if end(node) - offset >= 20 and struct.unpack_from("<I", data, offset + 8)[0] == ROTATION_TAG:
                angle = struct.unpack_from("<f", data, offset + 0x10)[0]
                if math.isfinite(angle) and abs(angle) < 1000:
                    angles.append(angle)
        leaf_angles[root_id] = angles

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
        while cursor not in seen:
            seen.add(cursor)
            if end(cursor) - offsets[cursor] >= 20 and struct.unpack_from(
                "<I", data, offsets[cursor] + 8
            )[0] == KEY_NODE_TAG:
                key = struct.unpack_from("<I", data, offsets[cursor] + 0x10)[0]
                break
            if parent[cursor] is None:
                break
            cursor = parent[cursor]
        root_id = f"0x{struct.unpack_from('<I', data, offsets[root_of(index)])[0]:08x}"
        points = [struct.unpack_from("<8f", data, offset + 48 + i * stride) for i in range(used)]
        curves.append((root_id, key, points))

    values = defaultdict(set)
    for root_id, key, points in curves:
        for point in points:
            for axis, value in (("y", point[5]), ("z", point[6])):
                if value != 0.0:
                    values[(axis, key)].add(value)

    random.seed(args.seed)
    rows = []
    for (axis, key), samples in sorted(values.items()):
        degrees = [abs(value) * 180.0 / math.pi for value in samples]
        for grid in GRIDS:
            def fraction_at_zero(items):
                hits = 0
                for value in items:
                    residual = abs(value - round(value / grid) * grid)
                    hits += residual < THRESHOLD
                return hits / len(items)

            observed = fraction_at_zero(degrees)
            baseline = []
            for _ in range(200):
                offset = random.random() * grid
                baseline.append(fraction_at_zero([value + offset for value in degrees]))
            rows.append((
                axis, f"0x{key:08x}" if key is not None else "", grid, len(samples),
                f"{observed:.4f}", f"{sum(baseline) / len(baseline):.4f}",
                f"{max(baseline):.4f}",
            ))

    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["axis", "key_hash", "grid_deg", "samples", "observed_lt_0.05", "baseline_mean", "baseline_max"])
        writer.writerows(rows)

    print("axis\tkey\tgrid\tsamples\tobserved\tbaseline_mean\tbaseline_max")
    for row in rows:
        print("\t".join(str(value) for value in row))

    # Leaf identity: same-root vs seeded cross-root permutations, matched by leaf count.
    by_count = defaultdict(list)
    for root_id, angles in leaf_angles.items():
        if angles:
            by_count[len(angles)].append(root_id)
    same_hits = 0
    total = 0
    for root_id, key, points in curves:
        angles = leaf_angles.get(root_id, [])
        if not angles:
            continue
        for point in points:
            for value in (point[5], point[6]):
                if value == 0.0:
                    continue
                total += 1
                same_hits += min(abs(abs(value) - abs(angle)) for angle in angles) <= 0.01
    baseline = []
    for _ in range(args.permutations):
        hits = 0
        for root_id, key, points in curves:
            angles = leaf_angles.get(root_id, [])
            if not angles:
                continue
            pool = by_count.get(len(angles), [])
            candidates = [item for item in pool if item != root_id]
            for point in points:
                for value in (point[5], point[6]):
                    if value == 0.0:
                        continue
                    if candidates:
                        other = leaf_angles[random.choice(candidates)]
                        hits += min(abs(abs(value) - abs(angle)) for angle in other) <= 0.01
        baseline.append(hits / total if total else 0.0)
    baseline.sort()
    print(f"\nleaf_same_root\t{same_hits}/{total}\t{same_hits/total if total else 0:.4f}")
    print(
        "leaf_permutation\tmean\t"
        f"{sum(baseline)/len(baseline):.4f}\tp95\t{baseline[int(len(baseline)*0.95)]:.4f}"
    )


if __name__ == "__main__":
    main()
