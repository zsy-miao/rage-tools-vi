"""Build the record -> section index for the script metadata corpora.

`PSIN` carries the sections and `LSCH` indexes them, so one table can join both
views. For every record this emits one row per section:

  record, tag, block_bytes, block_rows, index_bytes, index_small, index_subrecords

where `block_*` come from the `PSIN` descriptor and `index_*` from the matching
`LSCH` row (matched on the row's first word, verified to be a section tag in
200/200 records).

The point is to stop guessing field roles: with both views side by side, a field
either matches a measured quantity or it does not.

    python3 tools/script_sections.py --out handoff/script-sections.tsv
    python3 tools/script_sections.py --archive /path/levels.rpf \\
        --index output/index/levels.tsv --out cache/levels-sections.tsv
"""

import argparse
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import script_meta as sm


def index_rows(body, chunk):
    """Decode the LSCH rows: (tag, hash, small, count_word, subcount)."""
    rows = []
    base = chunk["offset"] + 8
    for position in range(chunk["count"]):
        entry = base + 32 * position
        tag, hash_value, small, _zero = struct.unpack_from("<IIII", body, entry)
        word = struct.unpack_from("<I", body, entry + 0x18)[0]
        subcount = struct.unpack_from("<H", body, entry + 0x1E)[0]
        rows.append({"tag": tag, "hash": hash_value, "small": small,
                     "word": word, "subcount": subcount})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive", type=Path, default=Path("script.rpf"))
    parser.add_argument("--index", type=Path, default=Path("output/index/script.tsv"))
    parser.add_argument("--out", type=Path, default=Path("handoff/script-sections.tsv"))
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if not args.archive.is_file() or not args.index.is_file():
        sys.exit("need the archive and its index")

    out = args.out.open("w")
    out.write("record\ttag\tblock_bytes\tblock_rows\tindex_hash\tindex_small"
              "\tindex_word\tindex_subrecords\n")

    records = 0
    matched = 0
    unmatched = 0
    correlation = defaultdict(Counter)
    tags = Counter()

    for record, body in sm.streams(args.archive, args.index):
        parsed = sm.parse_psin(body, 0)
        chunks = {chunk["magic"]: chunk for chunk in sm.walk(body)}
        if not parsed:
            continue
        records += 1
        blocks = []
        cursor = parsed["first_payload"]
        for descriptor in parsed["descriptors"]:
            blocks.append((descriptor["key"], descriptor["length"]))
            cursor += sm.align16(descriptor["length"])
        index = {}
        if "LSCH" in chunks:
            for row in index_rows(body, chunks["LSCH"]):
                index.setdefault(row["tag"], row)
        block_map = dict(blocks)
        for tag, length in blocks:
            row = index.get(tag)
            if row:
                matched += 1
                # does the index word equal the block's byte length, or its row count?
                rows_in_block = length // 16 if tag != 0xDE396FE2 else length // 16
                correlation["word==bytes"][row["word"] == length] += 1
                correlation["small==bytes"][row["small"] == length] += 1
                correlation["word==rows"][row["word"] == rows_in_block] += 1
                correlation["small==rows"][row["small"] == rows_in_block] += 1
                correlation["sub==rows"][row["subcount"] == rows_in_block] += 1
                out.write(f"{record}\t0x{tag:08x}\t{length}\t{rows_in_block}\t"
                          f"0x{row['hash']:08x}\t{row['small']}\t{row['word']}\t"
                          f"{row['subcount']}\n")
            else:
                unmatched += 1
                out.write(f"{record}\t0x{tag:08x}\t{length}\t{length // 16}\t\t\t\t\n")
            tags[tag] += 1
        del block_map
        if args.limit and records >= args.limit:
            break

    out.close()
    print(f"records {records}  sections {matched + unmatched}  "
          f"indexed {matched}  unindexed {unmatched}")
    print(f"distinct section tags: {len(tags)}")
    print("most common tags:", [(hex(t), c) for t, c in tags.most_common(8)])
    print("\nfield-vs-measurement agreement:")
    for name, counter in sorted(correlation.items()):
        yes = counter.get(True, 0)
        no = counter.get(False, 0)
        total = yes + no
        print(f"  {name:14s} {yes:6d}/{total:<6d} {yes / total if total else 0:.1%}")
    print(f"\nrows -> {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
