#!/usr/bin/env python3
"""Group class-0 roots by exact bone-hash sets and report shared templates."""
import argparse
import csv
import hashlib
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bones", type=Path, nargs="?", default=Path("handoff/script-bones.tsv"))
    parser.add_argument("--tsv", type=Path, default=Path("handoff/script-bone-templates.tsv"))
    args = parser.parse_args()

    roots = defaultdict(set)
    classes = {}
    with args.bones.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            roots[row["root_id"]].add(row["bone_hash"])
            classes[row["root_id"]] = row["root_class"]

    templates = defaultdict(list)
    for root, hashes in roots.items():
        signature = hashlib.sha256("\n".join(sorted(hashes)).encode()).hexdigest()
        templates[(signature, len(hashes))].append(root)

    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["template_id", "bone_count", "root_count", "roots", "hash_signature"])
        for index, ((signature, bone_count), group) in enumerate(
            sorted(templates.items(), key=lambda item: (-len(item[1]), -item[0][1], item[0][0])), start=1
        ):
            writer.writerow([f"T{index:02d}", bone_count, len(group), ",".join(sorted(group)), signature])

    print("templates\t" + str(len(templates)))
    print("template\tbones\troots\troot_ids")
    for index, ((signature, bone_count), group) in enumerate(
        sorted(templates.items(), key=lambda item: (-len(item[1]), -item[0][1], item[0][0])), start=1
    ):
        print(f"T{index:02d}\t{bone_count}\t{len(group)}\t{','.join(sorted(group))}")

    print("\nshared-hash frequency")
    counts = defaultdict(int)
    for hashes in roots.values():
        for name in hashes:
            counts[name] += 1
    for name, total in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]:
        print(f"{name}\t{total}")


if __name__ == "__main__":
    main()
