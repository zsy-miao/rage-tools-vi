"""Test candidate hash algorithms and name variants against project targets.

Targets come from four places:
  * the two `core_bvh4` descriptor ids  (`+0x40`/`+0x44`)
  * the class-0 bone-table hashes      (`handoff/script-bones.tsv`)
  * the `0x8f18aff0` weight hashes      (`handoff/script-pair-arrays.tsv`)
  * the ten `+0x28` header values       (`handoff/header-census-full.tsv`)

Names come from a harvested corpus (see `harvest_names.py`).  Each name is also
tried in case, extension, separator and mount-prefix variants, because RPF hashes
are usually taken over a normalized path.
"""

import argparse
import csv
import re
import struct
import zlib
from pathlib import Path

ALNUM = re.compile(r"[A-Za-z0-9]")


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


def fnv1a(text):
    value = 0x811C9DC5
    for byte in text.encode("utf-8", "ignore"):
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


def crc32(text):
    return zlib.crc32(text.encode("utf-8", "ignore")) & 0xFFFFFFFF


ALGORITHMS = {"joaat": joaat, "crc32": crc32, "fnv1a": fnv1a}

PREFIXES = ("", "common:/", "platform:/", "assets:/", "data/", "./")


def variants(name):
    seen = set()
    forms = {name, name.lower(), name.upper()}
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    if base:
        forms.add(base)
        forms.add(base.lower())
        if "." in base:
            stem = base.rsplit(".", 1)[0]
            forms.add(stem)
            forms.add(stem.lower())
    for form in list(forms):
        swapped = form.replace("/", "\\").replace("\\", "/")
        forms.add(swapped)
        for prefix in PREFIXES:
            if prefix and not form.startswith(prefix):
                forms.add(prefix + form)
    for form in forms:
        if form and form not in seen:
            seen.add(form)
            yield form


def load_targets(args):
    targets = {}

    descriptors = args.descriptors
    if descriptors.is_file():
        blob = descriptors.read_bytes()
        stride = 216
        values = set()
        for index in range(len(blob) // stride):
            words = struct.unpack_from("<52I", blob, index * stride + 8)
            values.add(words[16])
            values.add(words[17])
        targets["bvh4 ids"] = values

    bones = set()
    for row in csv.DictReader(args.bones.open(), delimiter="\t"):
        value = row.get("bone_hash", "")
        if value.startswith("0x"):
            bones.add(int(value, 16))
    targets["bone hashes"] = bones

    weights = set()
    for row in csv.DictReader(args.weights.open(), delimiter="\t"):
        value = row.get("hash", "")
        if value.startswith("0x"):
            weights.add(int(value, 16))
    targets["weight hashes"] = weights

    header = set()
    for row in csv.DictReader(args.census.open(), delimiter="\t"):
        header.add(int(row["mode"], 0) & 0x0)  # placeholder to keep the file open
        break
    header = set()
    for row in csv.DictReader(args.census.open(), delimiter="\t"):
        header.add(int(row["mode"], 0))
    targets["+0x28 values"] = {value for value in header if value < 0x100000000}
    return targets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("cache/name-corpus.txt"))
    parser.add_argument("--descriptors", type=Path, default=Path("cache/bvh4-descriptors.bin"))
    parser.add_argument("--bones", type=Path, default=Path("handoff/script-bones.tsv"))
    parser.add_argument("--weights", type=Path, default=Path("handoff/script-pair-arrays.tsv"))
    parser.add_argument("--census", type=Path, default=Path("handoff/header-census-full.tsv"))
    parser.add_argument("--min-alnum", type=float, default=0.6)
    args = parser.parse_args()

    targets = {name: values for name, values in load_targets(args).items() if values}
    for name, values in targets.items():
        print(f"target {name}: {len(values)}")

    names = [line.strip() for line in args.corpus.read_text().splitlines() if line.strip()]
    plausible = [
        name for name in names
        if len(ALNUM.findall(name)) / max(1, len(name)) >= args.min_alnum
    ]
    print(f"corpus: {len(names)} tokens, plausible: {len(plausible)}")

    hits = []
    tested = 0
    for name in plausible:
        for form in variants(name):
            tested += 1
            for algorithm, function in ALGORITHMS.items():
                value = function(form)
                for target_name, values in targets.items():
                    if value in values:
                        hits.append((target_name, algorithm, form, value))
                        print(f"HIT {target_name} {algorithm}({form!r}) = 0x{value:08x}")
    print(f"\nvariants tested: {tested:,}, hits: {len(hits)}")


if __name__ == "__main__":
    main()
