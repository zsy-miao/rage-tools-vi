"""Resolve PSIN class and field hashes against a text corpus.

The PSIN typed-property array stores `(value, type, property_hash, key_hash)`.
The earlier attempt hashed 7k names with 64-bit variants (JOAAT-64, FNV-64,
Murmur64A) and found nothing; the hashes are plain **JOAAT32 of lowercase
names**, and the corpus matters far more than the hash function.

    python3 tools/psin_name_probe.py --properties cache/psin-properties.tsv \\
        --corpus cache/name-corpus-all.txt tools/bone_names.txt \\
        --out handoff/psin-names.tsv

Coverage is reported with a collision budget: tokens x targets / 2^32. A run
that returns far more hits than the budget is evidence; a run near the budget is
not.
"""

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

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
    return value


def load_properties(path):
    """property/key hash -> (records, {types}, sample values)."""
    classes = defaultdict(lambda: [0, Counter(), []])
    fields = defaultdict(lambda: [0, Counter(), []])
    for row in csv.DictReader(path.open(), delimiter="\t"):
        kind = row["type"]
        for key, bucket in ((int(row["class_hash"], 16), classes),
                            (int(row["field_hash"], 16), fields)):
            entry = bucket[key]
            entry[0] += 1
            entry[1][kind] += 1
            if len(entry[2]) < 4:
                entry[2].append(row["value"])
    return classes, fields


def load_tokens(paths):
    tokens = set()
    for path in paths:
        if not path.is_file():
            continue
        for line in path.read_text(errors="ignore").splitlines():
            token = line.strip().lower()
            if TOKEN.match(token):
                tokens.add(token)
    return tokens


def resolve(targets, tokens):
    hits = {}
    for token in tokens:
        value = joaat(token)
        if value in targets and value not in hits:
            hits[value] = token
    return hits


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--properties", type=Path,
                        default=Path("cache/psin-properties.tsv"))
    parser.add_argument("--corpus", type=Path, nargs="*",
                        default=[Path("cache/name-corpus-all.txt")])
    parser.add_argument("--out", type=Path, default=Path("handoff/psin-names.tsv"))
    args = parser.parse_args()

    classes, fields = load_properties(args.properties)
    tokens = load_tokens(args.corpus)
    class_hits = resolve(classes, tokens)
    field_hits = resolve(fields, tokens)

    targets = len(classes) + len(fields)
    budget = len(tokens) * targets / 2 ** 32
    print(f"tokens {len(tokens)}; properties {len(classes)}; keys {len(fields)}")
    print(f"resolved properties {len(class_hits)} "
          f"({len(class_hits)/len(classes):.1%}); "
          f"keys {len(field_hits)} ({len(field_hits)/len(fields):.1%})")
    print(f"collision budget: {budget:.2f} expected false positives for "
          f"{len(class_hits) + len(field_hits)} hits")

    rows = []
    for kind, hits, source in (("property", class_hits, classes),
                               ("key", field_hits, fields)):
        for value, name in hits.items():
            records, types, _ = source[value]
            rows.append((kind, value, name, records,
                         ",".join(f"{k}:{v}" for k, v in types.most_common())))
    rows.sort(key=lambda row: (row[0], -row[3]))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as out:
        out.write("kind\thash\tname\trecords\ttypes\n")
        for kind, value, name, records, types in rows:
            out.write(f"{kind}\t0x{value:08x}\t{name}\t{records}\t{types}\n")
    print(f"wrote {args.out} ({len(rows)} rows)")
    for kind, value, name, records, types in rows[:12]:
        print(f"  {kind:5s} 0x{value:08x} {name:28s} records {records:>5}  {types}")


if __name__ == "__main__":
    main()
