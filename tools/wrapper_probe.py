"""Probe 32-byte +0x10 wrappers for a signature that predicts rotation leaves."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from object_names import extract_object, parse_tree  # noqa: E402
from root_names import candidates, joaat  # noqa: E402

ROTATION_HASH = 0xFC86DDE2


def layout(pointers):
    return ",".join(f"0x{field:02x}" for field, _ in pointers)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument(
        "--tsv", type=Path, default=Path("output/script.rpf/wrapper-probe.tsv")
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
        if end(index) - offsets[index] != 32 or [field for field, _ in links] != [0x10]:
            continue
        parent_index = parent[index]
        parent_name = None
        parent_layout = ""
        parent_field = ""
        parent_size = ""
        if parent_index is not None:
            parent_name = name_at(parent_index, 0) or name_at(parent_index, 0x10)
            parent_links = pointers(parent_index)
            parent_layout = layout(parent_links)
            parent_size = end(parent_index) - offsets[parent_index]
            for field, target in parent_links:
                if target == index:
                    parent_field = f"0x{field:02x}"
        target = links[0][1]
        target_links = pointers(target)
        target_size = end(target) - offsets[target]
        target_layout = layout(target_links)
        leaf = not target_links and target_size >= 12
        target_h08 = (
            struct.unpack_from("<I", data, offsets[target] + 0x08)[0] if leaf else None
        )
        rotation = target_h08 == ROTATION_HASH if leaf else None
        root = root_of[index]
        rows.append(
            {
                "wrapper": index,
                "wrapper_offset": offsets[index],
                "raw08": struct.unpack_from("<I", data, offsets[index] + 0x08)[0],
                "parent": parent_index,
                "parent_name": parent_name,
                "parent_field": parent_field,
                "parent_size": parent_size,
                "parent_layout": parent_layout,
                "target": target,
                "target_offset": offsets[target],
                "target_size": target_size,
                "target_layout": target_layout,
                "leaf": leaf,
                "target_h08": target_h08,
                "rotation": rotation,
                "root": root,
                "root_name": name_at(root, 0) if root is not None else None,
            }
        )

    part_controls = []
    for index in range(count):
        links = pointers(index)
        if end(index) - offsets[index] != 32 or [field for field, _ in links] != [0x18]:
            continue
        target = links[0][1]
        target_links = pointers(target)
        target_size = end(target) - offsets[target]
        if target_links or target_size < 12:
            continue
        target_h08 = struct.unpack_from("<I", data, offsets[target] + 0x08)[0]
        if target_h08 == ROTATION_HASH:
            part_controls.append(
                (index, name_at(index, 0) or name_at(index, 0x10), target)
            )

    out = args.tsv
    out.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "wrapper",
        "wrapper_offset",
        "raw08",
        "parent",
        "parent_name",
        "parent_field",
        "parent_size",
        "parent_layout",
        "target",
        "target_offset",
        "target_size",
        "target_layout",
        "leaf",
        "target_h08",
        "rotation",
        "root",
        "root_name",
    ]
    with out.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(columns) + "\n")
        for row in rows:
            handle.write(
                "\t".join(
                    "" if row[column] is None else str(row[column])
                    for column in columns
                )
                + "\n"
            )

    leaf_rows = [row for row in rows if row["leaf"]]
    rotation_rows = [row for row in leaf_rows if row["rotation"]]
    print(
        f"wrappers: {len(rows)}, leaf targets: {len(leaf_rows)}, "
        f"rotation leaves: {len(rotation_rows)} ({len(rotation_rows) / max(1, len(leaf_rows)):.1%})"
    )
    print(f"tsv: {out}")
    controls_tsv = out.with_name("part-rotation-controls.tsv")
    with controls_tsv.open("w", encoding="utf-8") as handle:
        handle.write(
            "part\tpart_offset\tname\ttarget\ttarget_offset\ttarget_h08\n"
        )
        for index, name, target in part_controls:
            handle.write(
                f"{index}\t0x{offsets[index]:x}\t{name or ''}\t{target}\t"
                f"0x{offsets[target]:x}\t0x{ROTATION_HASH:08x}\n"
            )
    print(
        f"+0x18 named-part controls: {len(part_controls)} direct rotation targets"
    )
    print(f"controls tsv: {controls_tsv}")
    for index, name, target in part_controls[:5]:
        print(
            f"  part {index} name={name} target={target} "
            f"target_offset=0x{offsets[target]:x}"
        )

    print("\nraw08 summary (leaf targets only)")
    groups = defaultdict(list)
    for row in leaf_rows:
        groups[row["raw08"]].append(row)
    print("raw08\tleaf\trot\tnamed_parent\ttarget_sizes\ttarget_layouts\tparent_names")
    for raw08, group in sorted(groups.items(), key=lambda item: -len(item[1]))[: args.limit]:
        named = sum(1 for row in group if row["parent_name"])
        sizes = Counter(row["target_size"] for row in group).most_common(4)
        layouts = Counter(row["target_layout"] for row in group).most_common(4)
        names = Counter(row["parent_name"] for row in group if row["parent_name"]).most_common(5)
        print(
            f"0x{raw08:08x}\t{len(group)}\t{sum(1 for row in group if row['rotation'])}\t"
            f"{named}\t{sizes}\t{layouts}\t{names}"
        )

    # Train/test split by root index parity. A signature is predictive if it
    # selects wrappers whose leaf target is the rotation hash.
    train = [row for row in leaf_rows if row["root"] is not None and row["root"] % 2 == 0]
    test = [row for row in leaf_rows if row["root"] is not None and row["root"] % 2 == 1]
    print(f"\ntrain wrappers: {len(train)}, test wrappers: {len(test)}")

    def evaluate(key, threshold=0.8, minimum=5):
        train_groups = defaultdict(list)
        test_groups = defaultdict(list)
        for row in train:
            train_groups[key(row)].append(row)
        for row in test:
            test_groups[key(row)].append(row)
        selected = set()
        for value, group in train_groups.items():
            if len(group) >= minimum:
                rate = sum(1 for row in group if row["rotation"]) / len(group)
                if rate >= threshold:
                    selected.add(value)
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
        return selected, tp, fp, fn, precision, recall

    signatures = {
        "raw08": lambda row: row["raw08"],
        "raw08+target_size": lambda row: (row["raw08"], row["target_size"]),
        "raw08+target_layout": lambda row: (row["raw08"], row["target_layout"]),
        "parent_name+raw08": lambda row: (row["parent_name"], row["raw08"]),
    }
    print("\nsignature evaluation (train roots even, test roots odd)")
    for name, key in signatures.items():
        selected, tp, fp, fn, precision, recall = evaluate(key)
        print(
            f"{name}: candidates={len(selected)} test tp={tp} fp={fp} fn={fn} "
            f"precision={precision:.2f} recall={recall:.2f}"
        )

    # Negative control and missed rotation examples.
    print("\nexamples")
    for row in rows[:3]:
        print(
            f"  wrapper {row['wrapper']} raw08=0x{row['raw08']:08x} "
            f"parent={row['parent']} {row['parent_name']} target={row['target']} "
            f"target_h08={row['target_h08']} rotation={row['rotation']}"
        )
    false_positives = [
        row
        for row in leaf_rows
        if row["raw08"] in evaluate(signatures["raw08"])[0] and not row["rotation"]
    ]
    missed = [
        row
        for row in leaf_rows
        if row["raw08"] not in evaluate(signatures["raw08"])[0] and row["rotation"]
    ]
    print(f"  false-positive candidates: {len(false_positives)}")
    for row in false_positives[:3]:
        print(
            f"    wrapper {row['wrapper']} parent={row['parent_name']} "
            f"target={row['target']} target_h08={row['target_h08']}"
        )
    print(f"  missed rotations: {len(missed)}")
    for row in missed[:3]:
        print(
            f"    wrapper {row['wrapper']} raw08=0x{row['raw08']:08x} "
            f"parent={row['parent_name']} target={row['target']}"
        )


if __name__ == "__main__":
    main()
