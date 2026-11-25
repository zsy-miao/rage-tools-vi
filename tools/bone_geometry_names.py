"""Predict bone names from geometry, inside a rig family.

Names are usually recovered by vocabulary, which has stalled at 99 of 612. This
takes the other route: a bone's *position in its rig* is independent of its hash.
Within a rig family the members are the same skeleton scaled differently, so a
named bone in one member predicts the bone at the same normalised position in
another.

Pipeline:

  1. normalise each bone centroid by the root's bounding box, so scale drops out;
  2. take the named bones of the same family as templates;
  3. for an unnamed bone, require the nearest template to be within `--max-distance`
     and clearly nearer than the runner-up (`--margin`).

    python3 tools/bone_geometry_names.py --out handoff/bone-geometry-candidates.tsv
"""
import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


def load_families(path):
    family = {}
    for row in csv.DictReader(path.open(), delimiter="\t"):
        for root in row["roots"].split(","):
            root = root.strip()
            if root:
                family[root] = row["family_id"]
    return family


TRUSTED = {"curated", "grammar"}


def load_names(path, trusted=TRUSTED):
    """Only trusted names may act as templates.

    A candidate that is really a JOAAT collision would project itself onto every
    member of the family, so untrusted names must never seed a prediction.
    """
    names = {}
    for row in csv.DictReader(path.open(), delimiter="\t"):
        if row.get("kind") == "bone" and row.get("confidence") in trusted:
            names[int(row["hash"], 16)] = row["name"]
    return names


def validate(bones, names, family, normalised, args):
    """Hide each named bone, predict it from the rest, and score the result."""
    correct = wrong = skipped = 0
    mistakes = []
    for root, rows in bones.items():
        fam = family.get(root)
        if not fam:
            continue
        for index, value, *_ in rows:
            if value not in names:
                continue
            point = normalised[root].get(index)
            if point is None:
                continue
            pool = [(names[other_value], normalised[other_root][other_index])
                    for other_root, other_rows in bones.items()
                    for other_index, other_value, *_ in other_rows
                    if other_value in names
                    and normalised[other_root].get(other_index) is not None
                    and not (other_root == root and other_index == index)]
            if not pool:
                continue
            scored = sorted((math.dist(point, template), name) for name, template in pool)
            best, second = scored[0], scored[1] if len(scored) > 1 else ((9, ""),)
            if best[0] > args.max_distance or second[0] - best[0] < args.margin:
                skipped += 1
                continue
            if best[1] == names[value]:
                correct += 1
            else:
                wrong += 1
                mistakes.append((names[value], best[1], round(best[0], 3)))
    total = correct + wrong
    print(f"leave-one-out: {correct} correct, {wrong} wrong "
          f"({correct / total:.0%} precision)" if total else "no predictions")
    print(f"  abstained: {skipped}")
    for want, got, distance in mistakes[:8]:
        print(f"  wanted {want:22s} predicted {got:22s} d={distance}")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--geometry", type=Path,
                        default=Path("handoff/script-bone-geometry.tsv"))
    parser.add_argument("--names", type=Path, default=Path("handoff/names.tsv"))
    parser.add_argument("--families", type=Path,
                        default=Path("handoff/script-bone-template-families.tsv"))
    parser.add_argument("--out", type=Path,
                        default=Path("handoff/bone-geometry-candidates.tsv"))
    parser.add_argument("--max-distance", type=float, default=0.08)
    parser.add_argument("--margin", type=float, default=0.02)
    parser.add_argument("--leave-one-out", action="store_true",
                        help="hide each named bone in turn and score the prediction")
    args = parser.parse_args()

    names = load_names(args.names)
    family = load_families(args.families)
    bones = defaultdict(list)
    for row in csv.DictReader(args.geometry.open(), delimiter="\t"):
        try:
            bones[row["root_id"]].append((
                int(row["bone_index"]), int(row["bone_hash"], 16),
                float(row["cx"]), float(row["cy"]), float(row["cz"])))
        except (KeyError, ValueError):
            continue

    normalised = {}
    for root, rows in bones.items():
        xs = [b[2] for b in rows] or [0.0]
        ys = [b[3] for b in rows] or [0.0]
        zs = [b[4] for b in rows] or [0.0]
        span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1e-6)
        mid = ((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, (max(zs) + min(zs)) / 2)
        normalised[root] = {
            index: ((x - mid[0]) / span, (y - mid[1]) / span, (z - mid[2]) / span)
            for index, _, x, y, z in rows}

    templates = defaultdict(list)
    for root, rows in bones.items():
        fam = family.get(root)
        if not fam:
            continue
        for index, value, *_ in rows:
            if value in names:
                point = normalised[root].get(index)
                if point:
                    templates[fam].append((names[value], point, root))

    if args.leave_one_out:
        return validate(bones, names, family, normalised, args)

    out_rows = []
    for root, rows in sorted(bones.items()):
        fam = family.get(root)
        if not fam or not templates[fam]:
            continue
        for index, value, *_ in rows:
            if value in names:
                continue
            point = normalised[root].get(index)
            if point is None:
                continue
            scored = sorted(
                ((math.dist(point, template_point), name, template_root)
                 for name, template_point, template_root in templates[fam]
                 if template_root != root))
            if len(scored) < 2:
                continue
            best, second = scored[0], scored[1]
            if best[0] > args.max_distance or second[0] - best[0] < args.margin:
                continue
            out_rows.append((root, fam, index, f"0x{value:08x}", best[1],
                             round(best[0], 4), round(second[0], 4)))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as out:
        out.write("root_id\tfamily\tbone_index\tbone_hash\tpredicted_name\t"
                  "distance\tsecond_distance\n")
        for row in out_rows:
            out.write("\t".join(str(c) for c in row) + "\n")
    print(f"{len(out_rows)} candidates -> {args.out}")
    by_name = defaultdict(int)
    for row in out_rows:
        by_name[row[4]] += 1
    print("most predicted names:", sorted(by_name.items(), key=lambda kv: -kv[1])[:8])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
