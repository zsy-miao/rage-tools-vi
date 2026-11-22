"""Resolve rig hashes against a large text corpus in tiers.

`tools/bone_name_probe.py` searches a curated anatomy vocabulary with a fixed
grammar. This tool does the opposite: it takes every token in a corpus (the
harvested archive strings, bone lists, and any XML/text on disk) and tries the
engine's naming shapes around it, cheapest shape first, so a 300k-token corpus
stays tractable.

Tiers, cheapest first:

  1. token                      (the corpus already contains full names)
  2. prefix+token, token+suffix (0..32, zero padded), side+token
  3. prefix+side+token+suffix   (only with --deep)

Every hit is `JOAAT(lowercase(name)) == hash`, so a hit is verified by
construction; the tool prints the shape that matched, which is what makes the
result readable rather than a pile of numbers.

    python3 tools/rig_name_corpus_probe.py --corpus cache/name-corpus-all.txt \\
        --bones handoff/script-bones.tsv --weights handoff/weight-hash-names.tsv \\
        --out handoff/rig-names-corpus.tsv [--deep]
"""

import argparse
import csv
import re
from pathlib import Path

PREFIXES = ("", "skel_", "mh_", "rb_", "ph_", "ik_", "mover_", "veh_", "pack_")
SIDES = ("", "l_", "r_", "c_", "m_")
SUFFIXES = ("",) + tuple(str(i) for i in range(0, 33)) \
    + tuple(f"{i:02d}" for i in range(0, 33))
TOKEN = re.compile(r"^[a-z][a-z0-9_]{1,40}$")


def joaat(text):
    value = 0
    for byte in text.encode():
        value = (value + byte) & 0xFFFFFFFF
        value = (value + (value << 10)) & 0xFFFFFFFF
        value ^= value >> 6
    value = (value + (value << 3)) & 0xFFFFFFFF
    value ^= value >> 11
    value = (value + (value << 15)) & 0xFFFFFFFF
    return value & 0xFFFFFFFF


def load_targets(bones, weights):
    targets = {}
    if bones and bones.is_file():
        for row in csv.DictReader(bones.open(), delimiter="\t"):
            value = row.get("bone_hash", "")
            if value.startswith("0x"):
                targets[int(value, 16)] = ("bone", row.get("root_id", ""),
                                           row.get("bone_index", ""))
    if weights and weights.is_file():
        for row in csv.DictReader(weights.open(), delimiter="\t"):
            value = row.get("weight_hash", "")
            if value.startswith("0x"):
                targets.setdefault(int(value, 16), ("weight", "", ""))
    return targets


def tokens(paths):
    seen = set()
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(errors="ignore").splitlines():
            token = line.strip().lower()
            if TOKEN.match(token):
                seen.add(token)
    return sorted(seen)


def search(targets, vocabulary, deep):
    hits = {}

    def try_name(name, shape):
        value = joaat(name)
        if value in targets and name not in hits:
            hits[name] = (value, shape)

    for token in vocabulary:
        try_name(token, "token")
        for prefix in PREFIXES:
            if prefix:
                try_name(prefix + token, "prefix+token")
        for side in SIDES:
            if side:
                try_name(side + token, "side+token")
        for suffix in SUFFIXES:
            if suffix:
                try_name(token + suffix, "token+suffix")
        if deep:
            for prefix in PREFIXES:
                for side in SIDES:
                    for suffix in SUFFIXES:
                        try_name(f"{prefix}{side}{token}{suffix}", "full")
    return hits


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, nargs="*",
                        default=[Path("cache/name-corpus-all.txt")])
    parser.add_argument("--bones", type=Path, default=Path("handoff/script-bones.tsv"))
    parser.add_argument("--weights", type=Path,
                        default=Path("handoff/weight-hash-names.tsv"))
    parser.add_argument("--out", type=Path,
                        default=Path("handoff/rig-names-corpus.tsv"))
    parser.add_argument("--deep", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="cap tokens (debug)")
    args = parser.parse_args()

    targets = load_targets(args.bones, args.weights)
    vocabulary = tokens(args.corpus)
    if args.limit:
        vocabulary = vocabulary[:args.limit]
    print(f"targets {len(targets)}; corpus tokens {len(vocabulary)}")
    print(f"shapes: {'full grammar' if args.deep else 'tiers 1-2'}")

    hits = search(targets, vocabulary, args.deep)
    shapes = {}
    for name, (value, shape) in hits.items():
        shapes[shape] = shapes.get(shape, 0) + 1
    print(f"resolved {len(hits)}; by shape {shapes}")

    rows = []
    for name, (value, shape) in hits.items():
        kind, root, index = targets[value]
        rows.append((value, name, kind, root, index, shape))
    rows.sort(key=lambda row: (row[2], row[3], int(row[4] or 0)))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as out:
        out.write("hash\tname\tkind\troot_id\tindex\tshape\n")
        for value, name, kind, root, index, shape in rows:
            out.write(f"0x{value:08x}\t{name}\t{kind}\t{root}\t{index}\t{shape}\n")
    print(f"wrote {args.out} ({len(rows)} rows)")
    for value, name, kind, root, index, shape in rows[:10]:
        print(f"  0x{value:08x}  {name:28s} {kind:6s} {shape}")


if __name__ == "__main__":
    main()
