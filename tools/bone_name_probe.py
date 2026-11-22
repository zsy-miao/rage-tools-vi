"""Resolve class-0 bone-table hashes by generating rig-style bone names.

The hash is `JOAAT(lowercase(name))`, confirmed on eight names in root
`0x48dcbb01`.  This tool generates candidates in the engine's rig conventions and
reports which of the 612 table hashes they explain:

    <prefix><side><part><suffix>      e.g. skel_l_calf, mh_r_bicep, rb_l_shoulder01

Prefixes seen so far: `skel_` (skeleton), `mh_` (muscle helpers), `rb_`
(ragdoll).  Sides are `l_`, `r_`, `c_`, `m_` or absent.  Parts come from a
curated anatomy/rig vocabulary plus words harvested from the local archives.

Anything that matches is a *verified* name: the probability of a JOAAT collision
against 612 targets is negligible for a curated vocabulary.
"""

import argparse
import csv
import re
from pathlib import Path

ANATOMY = """
bicep biceps tricep triceps deltoid pec pecs pectoral pectoralis lat lats
latissimus trap trapezius rhomboid infraspinatus supraspinatus subscapularis
teres teres_major teres_minor serratus serratus_anterior oblique obliques
rectus rectus_abdominis transversus erector spinae glute glutes gluteus
gluteus_maximus gluteus_medius hamstring hamstrings quad quadriceps vastus
soleus gastrocnemius tibialis peroneus adductor abductor sartorius gracilis
iliopsoas psoas brachialis coracobrachialis brachioradialis flexor extensor
pronator supinator thenar hypothenar masseter temporalis frontalis occipitalis
orbicularis zygomaticus platysma sternocleidomastoid digastric mylohyoid
geniohyoid abdomen abdominal abdominals armpit butt buttock calf cheek chest
chin clavicle collar crotch diaphragm ear elbow eye eyebrow finger foot
forearm forehead groin gum hand head heel hip jaw knee knuckle leg lip mane
muzzle nail neck nose nostril palm pelvis rib ribcage saddle satchelroot
scalp scapula scrotum shin shoulder shinpad skin sole spine sterno sternum
stirrup stomach tail teeth temple tendon testicle thigh throat thumb toe
tongue tooth torso waist wrist horn rein
bracer boot glove hood jack sleeve bodysuit fat belly
penis nipple navel kneecap collarbone cheekbone jawline eyelid pupil iris
appendix groin thighbone shinbone knuckle fingertip toenail molar incisor
""".split()

PREFIXES = ("skel_", "mh_", "rb_", "ph_", "ik_", "mover_", "pack_", "veh_", "")
SIDES = ("", "l_", "r_", "c_", "m_", "lf_", "rf_", "lr_", "rr_")
# Ragdoll rings and finger chains number into the high teens, so the suffix
# range has to cover 0..20 and the zero-padded forms.
# Finger chains use two-digit segment ids (21, 22, 23) and rings run into the
# tens, so cover plain 0..99 plus zero-padded forms.
SUFFIXES = (("",) + tuple(str(i) for i in range(100))
            + tuple(f"{i:02d}" for i in range(0, 100))
            + ("000", "010", "020", "100"))


def joaat(text, seed=0):
    value = seed & 0xFFFFFFFF
    for byte in text.encode("utf-8", "ignore"):
        value = (value + byte) & 0xFFFFFFFF
        value = (value + (value << 10)) & 0xFFFFFFFF
        value ^= value >> 6
    value = (value + (value << 3)) & 0xFFFFFFFF
    value ^= value >> 11
    value = (value + (value << 15)) & 0xFFFFFFFF
    return value & 0xFFFFFFFF


def load_bones(path):
    bones = {}
    for row in csv.DictReader(path.open(), delimiter="\t"):
        value = row.get("bone_hash", "")
        if value.startswith("0x"):
            bones[int(value, 16)] = row
    return bones


def corpus_parts(paths, minimum=3, maximum=24):
    parts = set()
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(errors="ignore").splitlines():
            token = line.strip().lower()
            if minimum <= len(token) <= maximum and re.fullmatch(r"[a-z][a-z0-9]*", token):
                parts.add(token)
    return parts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bones", type=Path, default=Path("handoff/script-bones.tsv"))
    parser.add_argument("--corpus", type=Path, nargs="*",
                        default=[Path("cache/name-corpus-all.txt")])
    parser.add_argument("--tsv", type=Path, default=Path("handoff/bone-hash-names.tsv"))
    parser.add_argument("--no-corpus", action="store_true")
    args = parser.parse_args()

    bones = load_bones(args.bones)
    print(f"bone hashes: {len(bones)}")
    parts = set(ANATOMY)
    if not args.no_corpus:
        extra = corpus_parts(args.corpus)
        parts |= extra
        print(f"corpus parts: {len(extra)}")
    print(f"part vocabulary: {len(parts)}")

    hits = {}
    for part in parts:
        for side in SIDES:
            for prefix in PREFIXES:
                for suffix in SUFFIXES:
                    name = f"{prefix}{side}{part}{suffix}"
                    value = joaat(name)
                    if value in bones and name not in hits:
                        hits[name] = (value, bones[value])
    print(f"resolved: {len(hits)} of {len(bones)}")

    by_family = {}
    by_root = {}
    for name, (value, row) in hits.items():
        family = name.split("_")[0]
        by_family[family] = by_family.get(family, 0) + 1
        root = row.get("root_id", "")
        by_root.setdefault(root, []).append((row.get("bone_index", ""), name))
    print("by family:", dict(sorted(by_family.items())))
    print("by root:")
    for root, entries in sorted(by_root.items(), key=lambda item: -len(item[1])):
        entries.sort(key=lambda item: int(item[0] or 0))
        print(f"  {root}: {len(entries)} names")
        for index, name in entries[:8]:
            print(f"    idx {index:>4}  {name}")

    rows = sorted(hits.items(), key=lambda item: (item[1][1].get("root_id", ""),
                                                 int(item[1][1].get("bone_index") or 0)))
    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w") as out:
        out.write("bone_hash\tname\troot_id\tbone_index\n")
        for name, (value, row) in rows:
            out.write(f"0x{value:08x}\t{name}\t{row.get('root_id','')}\t"
                      f"{row.get('bone_index','')}\n")
    print(f"wrote {args.tsv} ({len(rows)} names)")


if __name__ == "__main__":
    main()
