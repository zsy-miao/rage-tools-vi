"""Parse the PSIN typed property array and test 64-bit name-hash variants.

Rows come from the typed block (section tag `0x85b4c631`) and are read through
`script_meta`/`psin_blocks`, which follow the writer in the executable. The
16-byte row is

    u32 property; u32 key; u32 value; u32 type;   type in {0x101..0x105}

The **type word is last**. An earlier version of this tool sliced the record
8 bytes early and used `+4` as the type, which paired every value with the next
row's property; the numbers it printed (303 class hashes, 14,655 fields) were
that artefact. Corrected: 164 properties, 14,530 keys, 63,288 rows.

What the `value` word means is still open — it is mostly a declaration index, but
`Decay` carries a shared `300000` in the same block.

Modes:

    # inventory: how many records, types, distinct name hashes
    python3 tools/psin_property_tree.py

    # dump every record
    python3 tools/psin_property_tree.py --dump cache/psin-properties.tsv

    # try 64-bit hash variants of known names against the name-hash column
    python3 tools/psin_property_tree.py --hash-test
"""

import argparse
import csv
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import script_meta as sm
import psin_blocks as pb

TYPED_TAG = 0x85B4C631
TYPES = {0x101, 0x102, 0x103, 0x104, 0x105}
TYPE_NAMES = {0x101: "int", 0x102: "float", 0x103: "type103",
              0x104: "type104", 0x105: "type105"}


def sections(body):
    out = []
    offset = 0
    while offset + 8 <= len(body):
        tag = body[offset:offset + 4].decode("ascii", "ignore")
        size = struct.unpack_from(">I", body, offset + 4)[0]
        if not tag.isupper() or size < 8 or offset + size > len(body):
            break
        out.append((tag, offset, size))
        offset += size
    return out


def collect(archive, index):
    """Rows from the typed block, in the writer's field order."""
    records = []
    for position, body in sm.streams(archive, index):
        for tag, payload in pb.blocks(body):
            if tag != TYPED_TAG:
                continue
            for offset, prop, key, value, kind in pb.typed_rows(payload):
                records.append((position, offset, value, kind,
                                (prop << 32) | key))
    return records


# ---- 64-bit hash variants ------------------------------------------------

MASK64 = (1 << 64) - 1


def joaat64(text):
    value = 0
    for byte in text:
        value = (value + byte) & MASK64
        value = (value + (value << 10)) & MASK64
        value ^= value >> 6
    value = (value + (value << 3)) & MASK64
    value ^= value >> 11
    value = (value + (value << 15)) & MASK64
    return value


def fnv1a64(text):
    value = 0xcbf29ce484222325
    for byte in text:
        value ^= byte
        value = (value * 0x100000001b3) & MASK64
    return value


def murmur64a(text, seed=0):
    m = 0xc6a4a7935bd1e995
    r = 47
    length = len(text)
    value = (seed ^ (length * m)) & MASK64
    position = 0
    while length - position >= 8:
        (block,) = struct.unpack_from("<Q", text, position)
        block = (block * m) & MASK64
        block ^= block >> r
        block = (block * m) & MASK64
        value ^= block
        value = (value * m) & MASK64
        position += 8
    tail = text[position:]
    for index, byte in enumerate(reversed(tail)):
        value ^= byte << (index * 8)
    if tail:
        value = (value * m) & MASK64
    value ^= value >> r
    value = (value * m) & MASK64
    value ^= value >> r
    return value


VARIANTS = {"joaat64": joaat64, "fnv1a64": fnv1a64,
            "murmur64a": murmur64a,
            "murmur64a_seed1": lambda t: murmur64a(t, 1)}


def name_corpus():
    names = set()
    for path in list(Path("handoff").glob("*.tsv")):
        try:
            rows = list(csv.DictReader(path.open(), delimiter="\t"))
        except Exception:
            continue
        for row in rows:
            for column, value in row.items():
                if not value or not column:
                    continue
                lowered = column.lower()
                if ("name" in lowered or "path" in lowered or "root" in lowered) \
                        and len(value) < 96 and " " not in value.strip():
                    names.add(value.strip())
    return names


def hash_test(records):
    corpus = sorted(name_corpus())
    print(f"names in corpus: {len(corpus)}")
    wanted = {name for _, _, _, _, name in records}
    print(f"distinct name hashes to explain: {len(wanted)}")
    best = Counter()
    for variant, function in VARIANTS.items():
        hits = 0
        examples = []
        for name in corpus:
            for form in (name, name.lower(), name.upper(),
                         name.lower().rsplit(".", 1)[0]):
                encoded = form.encode()
                if function(encoded) in wanted:
                    hits += 1
                    if len(examples) < 3:
                        examples.append((form, hex(function(encoded))))
        best[variant] = hits
        print(f"  {variant:16s} hits {hits:>5}  examples {examples}")


def front_words(source, stride=8, limit_per_archive=1 << 24):
    """Every aligned u64 in the Front A and Front B regions of every archive."""
    words = {}
    headers = 0
    for path in sorted(source.glob("*.rpf")):
        size = path.stat().st_size
        with path.open("rb") as handle:
            for offset in range(0, max(0, size - 0x60), 0x4000):
                handle.seek(offset)
                header = handle.read(0x60)
                if len(header) < 0x60 or header[:4] != b"9FPR":
                    continue
                front_end = struct.unpack_from("<I", header, 4)[0]
                block = struct.unpack_from("<I", header, 8)[0]
                if not (0x60 < block <= front_end <= size - offset):
                    continue
                headers += 1
                handle.seek(offset + 0x10)
                for region in (handle.read(block - 0x10),
                               handle.read(front_end - block)):
                    for index in range(0, len(region) - 7, stride):
                        value = struct.unpack_from("<Q", region, index)[0]
                        words.setdefault(value, 0)
                        words[value] += 1
    return words, headers


def forms(name):
    lowered = name.replace("\\", "/").lower()
    leaf = lowered.rsplit("/", 1)[-1]
    stem = leaf.rsplit(".", 1)[0]
    return {name, lowered, leaf, stem, "platform:/" + lowered, lowered + "\0"}


def front_hash_test(source, names_path):
    """Test 64-bit name hashes against front-region u64 words.

    This is the wide-hash hypothesis: a table of 64-bit hashes is statistically
    identical to random bytes, so entropy cannot exclude it — only a hash
    function and a name corpus can.
    """
    names = []
    for row in csv.DictReader(names_path.open(), delimiter="\t"):
        if row.get("name"):
            names.append(row["name"])
    print(f"names: {len(names)}")
    words, headers = front_words(source)
    print(f"headers: {headers}  distinct u64 words: {len(words):,}")
    candidates = len(names) * 6 * len(VARIANTS)
    expected = candidates * len(words) / 2 ** 64
    hits = Counter()
    examples = []
    for name in names:
        for form in forms(name):
            encoded = form.encode()
            for variant, function in VARIANTS.items():
                value = function(encoded)
                if value in words:
                    hits[variant] += 1
                    if len(examples) < 10:
                        examples.append((variant, form, hex(value)))
    print(f"expected chance hits: {expected:.4f}")
    print("hits:", dict(hits) or "none")
    for example in examples:
        print("   ", example)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("script.rpf"))
    parser.add_argument("--index", type=Path, default=Path("output/index/script.tsv"))
    parser.add_argument("--dump", type=Path, help="write records as TSV")
    parser.add_argument("--hash-test", action="store_true")
    parser.add_argument("--front64", type=Path,
                        help="source directory of *.rpf to test 64-bit name hashes "
                             "against front-region u64 words")
    parser.add_argument("--names", type=Path, default=Path("handoff/names.tsv"))
    args = parser.parse_args()

    records = collect(args.archive, args.index)
    print(f"records: {len(records):,} across "
          f"{len({r[0] for r in records})} PSIN sections")
    kinds = Counter(record[3] for record in records)
    print("types:", {TYPE_NAMES[k]: n for k, n in kinds.most_common()})
    classes = Counter(record[4] & 0xffffffff for record in records)
    fields = Counter(record[4] >> 32 for record in records)
    print(f"distinct keys: {len(classes):,}; distinct properties: "
          f"{len(fields):,}")
    print(f"rows per key: max {max(classes.values()):,}; "
          f"top key {classes.most_common(1)[0][1]:,} rows")
    per = Counter(record[0] for record in records)
    counts = sorted(per.values())
    print(f"per PSIN section: min {counts[0]}, median {counts[len(counts)//2]}, "
          f"max {counts[-1]}")

    if args.front64:
        front_hash_test(args.front64, args.names)
        return 0

    if args.dump:
        args.dump.parent.mkdir(parents=True, exist_ok=True)
        with args.dump.open("w") as handle:
            handle.write("psin\toffset\tvalue\ttype\tclass_hash\tfield_hash\tas_float\n")
            for section, offset, value, kind, name in records:
                as_float = struct.unpack("<f", struct.pack("<I", value))[0]
                handle.write(f"{section}\t0x{offset:x}\t0x{value:08x}\t"
                             f"0x{kind:03x}\t0x{name & 0xffffffff:08x}\t"
                             f"0x{name >> 32:08x}\t{as_float:g}\n")
        print(f"wrote {args.dump}")

    if args.hash_test:
        hash_test(records)


if __name__ == "__main__":
    main()
