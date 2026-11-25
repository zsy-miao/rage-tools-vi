"""Analyze +0x18 named records and their direct rotation targets."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from object_names import extract_object, parse_tree  # noqa: E402
from root_names import candidates, joaat  # noqa: E402

ROTATION_HASH = 0xFC86DDE2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--tsv", type=Path, default=Path("output/script.rpf/rotation-parts.tsv")
    )
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    count, offsets, roots, children, root_of = parse_tree(data)
    by_address = {offset + 8: index for index, offset in enumerate(offsets)}
    names = set(candidates(Path("."), True))
    bone_names = Path("tools/bone_names.txt")
    if bone_names.is_file():
        names |= {line.strip() for line in bone_names.read_text().splitlines() if line.strip()}
    lookup = {}
    for name in names:
        for variant in {name, name.lower()}:
            lookup.setdefault(joaat(variant), set()).add(variant)

    def end(index):
        return offsets[index + 1] if index + 1 < count else len(data)

    def name_at(index, field):
        if offsets[index] + field + 4 > end(index):
            return None
        value = struct.unpack_from("<I", data, offsets[index] + field)[0]
        labels = lookup.get(value)
        return sorted(labels)[0] if labels else None

    def pointers(index):
        result = []
        for position in range(offsets[index], end(index) - 7, 8):
            address, tag = struct.unpack_from("<II", data, position)
            if tag == 0x71717171 and address in by_address:
                result.append((position - offsets[index], by_address[address]))
        return result

    parent = [None] * count
    for source, targets in enumerate(children):
        for target in targets:
            parent[target] = source

    rows = []
    for index in range(count):
        links = pointers(index)
        if end(index) - offsets[index] != 32 or [field for field, _ in links] != [0x18]:
            continue
        name0 = name_at(index, 0)
        name10 = name_at(index, 0x10)
        kind = "root" if name0 else ("part" if name10 else "unnamed")
        parent_index = parent[index]
        parent_links = pointers(parent_index) if parent_index is not None else []
        parent_field = ""
        for field, target in parent_links:
            if target == index:
                parent_field = f"0x{field:02x}"
        target = links[0][1]
        target_links = pointers(target)
        target_size = end(target) - offsets[target]
        leaf = not target_links and target_size >= 20
        target_h08 = (
            struct.unpack_from("<I", data, offsets[target] + 0x08)[0] if leaf else None
        )
        angle_raw = (
            struct.unpack_from("<I", data, offsets[target] + 0x10)[0] if leaf else None
        )
        angle = struct.unpack("<f", struct.pack("<I", angle_raw))[0] if leaf else None
        rotation = target_h08 == ROTATION_HASH if leaf else None
        rows.append(
            {
                "record": index,
                "offset": offsets[index],
                "kind": kind,
                "name0": name0,
                "name10": name10,
                "parent": parent_index,
                "record_h08": struct.unpack_from("<I", data, offsets[index] + 8)[0],
                "parent_name": name_at(parent_index, 0) or name_at(parent_index, 0x10)
                if parent_index is not None
                else None,
                "parent_field": parent_field,
                "parent_size": end(parent_index) - offsets[parent_index]
                if parent_index is not None
                else "",
                "parent_layout": ",".join(
                    f"0x{field:02x}" for field, _ in parent_links
                ),
                "parent_h08": struct.unpack_from("<I", data, offsets[parent_index] + 8)[0]
                if parent_index is not None
                else None,
                "target": target,
                "target_offset": offsets[target],
                "target_size": target_size,
                "target_layout": ",".join(f"0x{field:02x}" for field, _ in target_links),
                "leaf": leaf,
                "target_h08": target_h08,
                "target_word8": struct.unpack_from("<I", data, offsets[target] + 8)[0],
                "angle_raw": angle_raw,
                "angle": angle,
                "rotation": rotation,
                "root": root_of[index],
                "root_name": name_at(root_of[index], 0) if root_of[index] is not None else None,
            }
        )

    out = args.tsv
    out.parent.mkdir(parents=True, exist_ok=True)
    columns = list(rows[0]) if rows else []
    with out.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(columns) + "\n")
        for row in rows:
            handle.write(
                "\t".join("" if row[column] is None else str(row[column]) for column in columns)
                + "\n"
            )

    leaf_rows = [row for row in rows if row["leaf"]]
    rotation_rows = [row for row in leaf_rows if row["rotation"]]
    print(f"+0x18 records: {len(rows)}, leaf targets: {len(leaf_rows)}, rotations: {len(rotation_rows)}")
    print("kind\tcount\tleaf\trotation\tother_tags")
    for kind in ("root", "part", "unnamed"):
        group = [row for row in rows if row["kind"] == kind]
        leaves = [row for row in group if row["leaf"]]
        rot = sum(1 for row in leaves if row["rotation"])
        tags = Counter(
            row["target_h08"] for row in leaves if not row["rotation"] and row["target_h08"]
        ).most_common(5)
        print(f"{kind}\t{len(group)}\t{len(leaves)}\t{rot}\t{tags}")

    negative = sum(1 for row in leaf_rows if not row["rotation"])
    print(f"negative leaf targets: {negative}")
    print("\ntarget tags (all direct targets)")
    for tag, total in Counter(
        row["target_word8"] for row in rows if row["target_word8"] is not None
    ).most_common(args.limit):
        rot = sum(
            1
            for row in leaf_rows
            if row["target_h08"] == tag and row["rotation"]
        )
        print(f"  0x{tag:08x}\t{total}\trotation_leaf={rot}")

    print("\nrotation examples")
    for row in rotation_rows[:8]:
        print(
            f"  rec {row['record']} kind={row['kind']} name0={row['name0']} "
            f"name10={row['name10']} part_offset=0x{row['offset']:x} "
            f"target=0x{row['target_offset']:x} tag=0x{row['target_h08']:08x} "
            f"angle_raw=0x{row['angle_raw']:08x} angle={row['angle']}"
        )

    non_leaf = [
        row for row in rows if not row["leaf"] and (row["name10"] or row["name0"])
    ]
    print("\nnon-leaf controls")
    for row in non_leaf[:5]:
        print(
            f"  rec {row['record']} kind={row['kind']} name0={row['name0']} "
            f"name10={row['name10']} part_offset=0x{row['offset']:x} "
            f"target=0x{row['target_offset']:x} target_word8=0x{row['target_word8']:08x}"
        )

    # Parent-field predictor test, excluding the part name itself.
    labeled = [row for row in leaf_rows if row["root"] is not None and row["rotation"] is not None]
    train = [row for row in labeled if row["root"] % 2 == 0]
    test = [row for row in labeled if row["root"] % 2 == 1]
    features = {
        "kind": lambda row: row["kind"],
        "root_name": lambda row: row["root_name"],
        "parent_name": lambda row: row["parent_name"],
        "parent_size": lambda row: row["parent_size"],
        "parent_layout": lambda row: row["parent_layout"],
        "parent_h08": lambda row: row["parent_h08"],
        "part_h08": lambda row: row["record_h08"],
        "parent_field": lambda row: row["parent_field"],
        "root+parent": lambda row: (row["root_name"], row["parent_name"]),
    }
    print(f"\nparent-field predictor (train {len(train)}, test {len(test)})")
    if negative == 0:
        print("  degenerate: zero negative leaf targets; the leaf tag is the only reliable discriminator")
    for name, key in features.items():
        train_groups = defaultdict(list)
        test_groups = defaultdict(list)
        for row in train:
            train_groups[key(row)].append(row)
        for row in test:
            test_groups[key(row)].append(row)
        selected = {
            value
            for value, group in train_groups.items()
            if len(group) >= 5
            and sum(1 for row in group if row["rotation"]) / len(group) >= 0.8
        }
        tp = fp = fn = 0
        for row in test:
            predicted = key(row) in selected
            actual = bool(row["rotation"])
            if predicted and actual:
                tp += 1
            elif predicted and not actual:
                fp += 1
            elif not predicted and actual:
                fn += 1
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        print(
            f"  {name}: keys={len(selected)} tp={tp} fp={fp} fn={fn} "
            f"precision={precision:.2f} recall={recall:.2f}"
        )

    # Repeated part names across distinct roots: general vs vehicle-specific angle.
    pairs = defaultdict(list)
    for row in rotation_rows:
        if row["name10"]:
            pairs[row["name10"]].append(row)
    print("\nrepeated part names across roots")
    pairs_tsv = out.with_name("rotation-pairs.tsv")
    with pairs_tsv.open("w", encoding="utf-8") as handle:
        handle.write("part_name\trecords\troots\tangles\n")
        for name, group in sorted(pairs.items(), key=lambda item: -len(item[1])):
            angles = Counter(round(row["angle"], 5) for row in group)
            roots_seen = len({row["root"] for row in group})
            handle.write(
                f"{name}\t{len(group)}\t{roots_seen}\t"
                + ",".join(f"{angle}:{count}" for angle, count in angles.most_common())
                + "\n"
            )
    for name, group in sorted(pairs.items(), key=lambda item: -len(item[1]))[: args.limit]:
        angles = Counter(round(row["angle"], 5) for row in group)
        roots_seen = len({row["root"] for row in group})
        print(f"  {name}: records={len(group)} roots={roots_seen} angles={angles.most_common(4)}")

    print(f"\ntsv: {out}")
    print(f"pairs tsv: {pairs_tsv}")


if __name__ == "__main__":
    main()
