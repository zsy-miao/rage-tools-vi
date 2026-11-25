"""Decode the five PSIN blocks with the writer's own field order.

`tools/script_meta.py` recovers the chunk chain.  This tool goes inside `PSIN`,
where every record carries about five independently shaped blocks keyed by a
small set of constant tags.

Verified block shapes (from `FUN_144083410` and from decoding all 1,012 records):

  tag 0x85b4c631  typed rows, 16 bytes each: `{u32 a, u32 b, u32 c, u32 type}`
                  with `type` at **+0x0c** in 63,288 of 63,290 occurrences.
  tag 0xde396fe2  exactly 80 bytes: five 16-byte entries `(count, count, kind, 0)`
                  — a directory of sub-tables, not data.
  tag 0x01393259  variable; struct-like words with 0xffffffff sentinels.
  tag 0x16        variable, 16-byte rows, looks like 128-bit hash material.
  tag 0xaeb623d8  variable, 12-byte triples `{u32, f32, f32}` with the two floats
                  in narrow, world-coordinate-looking ranges.

Correction this tool embodies: `tools/psin_extract.py` sliced the record at
`offset + 8`, which puts its 16-byte grid **8 bytes early** relative to the real
rows.  Its "type" column was therefore the real `+0x0c` word (correct by
accident), but its `class_hash` and `field_hash` columns come from the *next*
physical row.  Columns map as: old `value` = new `c`, old `type` = new `type`,
old `class_hash` = next row's `a`, old `field_hash` = next row's `b`.

  python3 tools/psin_blocks.py --index output/index/script.tsv
  python3 tools/psin_blocks.py --index output/index/script.tsv --rows cache/psin-rows.tsv
"""

import argparse
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import script_meta as sm

TAGS = {
    0x85B4C631: "rows",
    0xDE396FE2: "directory",
    0x01393259: "struct",
    0x00000016: "hashes",
    0xAEB623D8: "triples",
}

TYPES = {0x101: "int", 0x102: "float", 0x103: "hash", 0x104: "bool", 0x105: "byte"}


def blocks(body):
    """Yield (tag, payload) for every PSIN descriptor of one record."""
    parsed = sm.parse_psin(body, 0)
    if not parsed:
        return
    cursor = parsed["first_payload"]
    for descriptor in parsed["descriptors"]:
        yield descriptor["key"], body[cursor:cursor + descriptor["length"]]
        cursor += sm.align16(descriptor["length"])


def typed_rows(payload):
    for offset in range(0, len(payload) - 15, 16):
        a, b, c, kind = struct.unpack_from("<IIII", payload, offset)
        yield offset, a, b, c, kind


def directory(payload):
    entries = []
    for offset in range(0, len(payload) - 15, 16):
        count, count2, kind, zero = struct.unpack_from("<IIII", payload, offset)
        entries.append((count, count2, kind, zero))
    return entries


def triples(payload):
    out = []
    for offset in range(0, len(payload) - 11, 12):
        word = struct.unpack_from("<I", payload, offset)[0]
        first, second = struct.unpack_from("<ff", payload, offset + 4)
        out.append((word, first, second))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--index", type=Path, default=Path("output/index/script.tsv"))
    parser.add_argument("--rows", type=Path, help="write typed rows to this TSV")
    parser.add_argument("--properties", type=Path,
                        help="write the legacy column layout with corrected pairing")
    parser.add_argument("--show", type=int, default=1, help="records to print")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if not args.archive.is_file() or not args.index.is_file():
        sys.exit("need the archive and its index")

    shape = Counter()
    tag_lengths = defaultdict(Counter)
    type_words = Counter()
    row_total = 0
    dir_kinds = Counter()
    triple_ranges = [1e9, -1e9, 1e9, -1e9]
    printed = 0
    out = args.rows.open("w") if args.rows else None
    if out:
        out.write("record\toffset\ta\tb\tc\ttype\ttype_name\n")
    legacy = args.properties.open("w") if args.properties else None
    if legacy:
        # same columns as cache/psin-properties.tsv, now with the correct pairing:
        # class_hash is this row's property, field_hash is this row's key.
        legacy.write("psin\toffset\tvalue\ttype\tclass_hash\tfield_hash\tas_float\n")

    for record, body in sm.streams(args.archive, args.index):
        if args.limit and record >= args.limit:
            break
        for tag, payload in blocks(body):
            role = TAGS.get(tag, "unknown")
            shape[role] += 1
            tag_lengths[tag][len(payload)] += 1
            if role == "rows":
                for offset, a, b, c, kind in typed_rows(payload):
                    row_total += 1
                    type_words[kind] += 1
                    if out:
                        out.write(f"{record}\t0x{offset:x}\t0x{a:08x}\t0x{b:08x}\t0x{c:08x}\t"
                                  f"0x{kind:03x}\t{TYPES.get(kind, '?')}\n")
                    if legacy:
                        as_float = struct.unpack("<f", struct.pack("<I", c))[0]
                        legacy.write(f"{record}\t0x{offset:x}\t0x{c:08x}\t0x{kind:03x}\t"
                                     f"0x{a:08x}\t0x{b:08x}\t{as_float:g}\n")
            elif role == "directory":
                for count, count2, kind, zero in directory(payload):
                    dir_kinds[kind] += 1
            elif role == "triples":
                for word, first, second in triples(payload):
                    triple_ranges[0] = min(triple_ranges[0], first)
                    triple_ranges[1] = max(triple_ranges[1], first)
                    triple_ranges[2] = min(triple_ranges[2], second)
                    triple_ranges[3] = max(triple_ranges[3], second)
            if printed < args.show and role in ("rows", "directory", "triples"):
                printed += 0  # print once per record below
        if printed < args.show:
            printed += 1
            print(f"\nrecord {record}: body {len(body)} B")
            for tag, payload in blocks(body):
                role = TAGS.get(tag, "unknown")
                print(f"  {role:9s} tag 0x{tag:08x} {len(payload):5d} B  {payload[:16].hex()}")
                if role == "rows":
                    for offset, a, b, c, kind in list(typed_rows(payload))[:5]:
                        print(f"      a 0x{a:08x} b 0x{b:08x} c {c:6d} type {TYPES.get(kind, hex(kind))}")
                if role == "directory":
                    for count, count2, kind, zero in directory(payload):
                        print(f"      count {count:4d} count2 {count2:4d} kind {kind} pad {zero}")
                if role == "triples":
                    for word, first, second in list(triples(payload))[:4]:
                        print(f"      word 0x{word:08x} f {first:8.3f} {second:8.3f}")

    if out:
        out.close()
        print(f"\ntyped rows -> {args.rows}")
    if legacy:
        legacy.close()
        print(f"legacy layout (corrected pairing) -> {args.properties}")
    print("\nblocks per role:", dict(shape))
    print("typed rows:", row_total)
    print("type words:", {TYPES.get(k, hex(k)): v for k, v in type_words.most_common()})
    print("directory kinds:", dict(dir_kinds))
    print(f"triple ranges: first {triple_ranges[0]:.2f}..{triple_ranges[1]:.2f}  "
          f"second {triple_ranges[2]:.2f}..{triple_ranges[3]:.2f}")
    for tag, lengths in sorted(tag_lengths.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"  tag 0x{tag:08x}: {sum(lengths.values())} blocks, "
              f"lengths {lengths.most_common(4)}, min {min(lengths)}, max {max(lengths)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
