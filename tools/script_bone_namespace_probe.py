#!/usr/bin/env python3
"""Cross-check skeleton family hashes against the named vehicle mover tables."""

import argparse
from collections import defaultdict
import csv
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from root_names import joaat


MODULUS = 1 << 32
MASK = MODULUS - 1
ROUND_INVERSE = pow(1 + (1 << 10), -1, MODULUS)
FINAL_FIRST_INVERSE = pow(9, -1, MODULUS)
FINAL_LAST_INVERSE = pow(1 + (1 << 15), -1, MODULUS)


def rows(path):
    with path.open(newline="", encoding="utf-8") as source:
        yield from csv.DictReader(source, delimiter="\t")


def family_rows(directory):
    cluster = Path(__file__).with_name("bone_template_families.py")
    with TemporaryDirectory() as workdir:
        output = Path(workdir) / "families.tsv"
        subprocess.run(
            [sys.executable, str(cluster), str(directory / "script-bones.tsv"),
             "--geometry", str(directory / "script-bone-geometry.tsv"), "--tsv", str(output)],
            check=True, stdout=subprocess.DEVNULL,
        )
        return list(rows(output))


def ordered_bones(path):
    roots = defaultdict(dict)
    for row in rows(path):
        root, index = int(row["root_id"], 16), int(row["bone_index"])
        if index in roots[root]:
            raise ValueError(f"Duplicate bone index {index} for root {root:#x} in {path}")
        roots[root][index] = int(row["bone_hash"], 16)
    return {root: tuple(bones[i] for i in range(len(bones))) for root, bones in roots.items()}


def undo_xor_shift(word, bits):
    result = word
    for shift in range(bits, 32, bits):
        result ^= word >> shift
    return result


def recover_joaat_seed(name, digest):
    word = (digest * FINAL_LAST_INVERSE) & MASK
    word = (undo_xor_shift(word, 11) * FINAL_FIRST_INVERSE) & MASK
    for byte in reversed(name.encode()):
        word = ((undo_xor_shift(word, 6) * ROUND_INVERSE) - byte) & MASK
    return word


def shared_seeds(words, names):
    evidence = defaultdict(list)
    for name in sorted(names):
        for word in sorted(words):
            evidence[recover_joaat_seed(name, word)].append((name, word))
    return {seed: pairs for seed, pairs in evidence.items()
            if len({name for name, _ in pairs}) >= 2
            and len({word for _, word in pairs}) >= 2}


def swapped(words):
    return {int.from_bytes(word.to_bytes(4, "little"), "big") for word in words}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff", type=Path, nargs="?", default=Path("handoff"))
    args = parser.parse_args()
    bones = ordered_bones(args.handoff / "script-bones.tsv")
    geometry = ordered_bones(args.handoff / "script-bone-geometry.tsv")
    if geometry != bones:
        raise ValueError("The bone and geometry exports disagree on per-root order")

    templates = defaultdict(set)
    for row in rows(args.handoff / "script-bone-templates.tsv"):
        members = [int(root, 16) for root in row["roots"].split(",")]
        for root in members:
            templates[root].add(row["template_id"])
        if len({frozenset(bones[root]) for root in members}) != 1:
            raise ValueError(f"Exact-set template disagrees with bones: {row['template_id']}")
    if templates.keys() != bones.keys() or any(len(ids) != 1 for ids in templates.values()):
        raise ValueError("Exact-set templates do not partition the bone roots")

    vehicle_rows = list(rows(args.handoff / "script-vehicle-curves.tsv"))
    models = {(row["root_name"], int(row["root_id"], 16)) for row in vehicle_rows
              if row["root_name"]}
    keys = {int(row["key_hash"], 16) for row in vehicle_rows}
    parts = {(row["key_name"], int(row["key_hash"], 16)) for row in vehicle_rows
             if row["key_name"]}
    known = models | parts
    if any(joaat(name) != word or recover_joaat_seed(name, word) != 0 for name, word in known):
        raise ValueError("Known vehicle names failed JOAAT positive controls")
    model_words = {word for _, word in models}
    mover_bases = {joaat(name.removesuffix("_mover")) for name, _ in parts
                   if name.endswith("_mover")}
    print(f"{len(models)} model and {len(parts)} named part controls passed JOAAT, "
          f"{len(keys)} curve key words, {len(mover_bases)} mover-base spellings, "
          f"{sum(map(len, bones.values()))} ordered rows agree with geometry", file=sys.stderr)

    families = family_rows(args.handoff)
    root_families = {
        int(root, 16): family["family_id"]
        for family in families for root in family["roots"].split(",")
    }
    all_bones = set().union(*(set(order) for order in bones.values()))
    model_seeds = shared_seeds(bones.keys(), {name for name, _ in models})
    part_seeds = shared_seeds(all_bones, {name for name, _ in parts})
    for namespace, evidence in (("model", model_seeds), ("part", part_seeds)):
        print(f"{namespace}: {len(evidence)} shared seeds across distinct name/word pairs",
              file=sys.stderr)
        for seed, pairs in sorted(evidence.items()):
            stems = {name.rstrip("0123456789") for name, _ in pairs}
            assignments = ", ".join(
                f"{name}={word:#010x}" + (f" ({root_families[word]})" if namespace == "model" else "")
                for name, word in pairs
            )
            print(f"  {seed:#010x}, {len(stems)} distinct stems: {assignments}", file=sys.stderr)

    writer = csv.writer(sys.stdout, delimiter="\t", lineterminator="\n")
    writer.writerow(("family", "roots", "exact_templates", "ordered_templates", "core_bones",
                     "union_bones", "model_root_matches", "swapped_model_root_matches",
                     "model_bone_matches", "swapped_model_bone_matches", "curve_key_bone_matches",
                     "swapped_curve_key_bone_matches", "mover_base_bone_matches"))
    for family in families:
        members = {int(root, 16) for root in family["roots"].split(",")}
        orders = {bones[root] for root in members}
        union = set.union(*(set(order) for order in orders))
        exact_templates = set.union(*(templates[root] for root in members))
        writer.writerow((
            family["family_id"], len(members), len(exact_templates), len(orders),
            family["core_bones"], len(union), len(members & model_words),
            len(swapped(members) & model_words), len(union & model_words),
            len(swapped(union) & model_words), len(union & keys), len(swapped(union) & keys),
            len(union & mover_bases),
        ))


if __name__ == "__main__":
    main()
