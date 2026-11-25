"""Read every header listed in a census TSV and analyze the header words.

`tools/header_census.py` records the parsed fields.  This tool re-reads the
0x60-byte header for each census row and reports, per word offset, the number
of distinct values and how each word relates to the parsed count, region
sizes, and mode.  It also lists the words that are constant across the whole
census, which are the fixed invariants of the format.

Archive paths are resolved against --source unless the census name is absolute.
"""

import argparse
import struct
from collections import Counter, defaultdict
from pathlib import Path

WORDS = 0x60 // 4


def align16(value):
    return (value + 15) // 16 * 16


def load_census(path):
    rows = []
    with path.open() as handle:
        header = handle.readline().rstrip("\n").split("\t")
        for line in handle:
            row = dict(zip(header, line.rstrip("\n").split("\t")))
            row["offset"] = int(row["offset"], 0)
            for field in ("mode", "version", "count", "size_b", "front_a", "trailer"):
                row[field] = int(row[field])
            rows.append(row)
    return rows


def resolve(source, name):
    direct = source / name
    if direct.is_file():
        return direct
    matches = [path for path in source.rglob(name) if path.is_file()]
    if len(matches) == 1:
        return matches[0]
    raise SystemExit(f"cannot resolve {name} under {source} ({len(matches)} matches)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, default=Path("handoff/header-census-full.tsv"))
    parser.add_argument("--source", type=Path,
                        default=Path("/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK"))
    parser.add_argument("--words", action="store_true", help="print the per-word summary")
    parser.add_argument("--dump", type=Path, help="write every header word to this TSV")
    parser.add_argument("--limit", type=int, default=0,
                        help="analyze at most this many census rows (sampled evenly)")
    args = parser.parse_args()

    rows = load_census(args.census)
    if args.limit and len(rows) > args.limit:
        step = len(rows) / args.limit
        rows = [rows[int(index * step)] for index in range(args.limit)]
    caches = {}
    for row in rows:
        name = row["archive"]
        if name not in caches:
            path = resolve(args.source, name)
            caches[name] = path.open("rb")
        handle = caches[name]
        handle.seek(row["offset"])
        header = handle.read(0x60)
        row["words"] = struct.unpack("<%dI" % WORDS, header)
    for handle in caches.values():
        handle.close()

    print(f"rows: {len(rows)}")
    print(f"archives: {len({row['archive'] for row in rows})}")

    if args.dump:
        args.dump.parent.mkdir(parents=True, exist_ok=True)
        with args.dump.open("w") as out:
            header = [
                "archive", "offset", "mode", "version", "count",
                "front_end", "block", "size_b", "front_a", "trailer",
            ] + [f"w{4 * index:02x}" for index in range(WORDS)]
            out.write("\t".join(header) + "\n")
            for row in rows:
                fields = [
                    row["archive"], f"0x{row['offset']:x}",
                ] + [str(row[name]) for name in
                     ("mode", "version", "count", "front_end", "block",
                      "size_b", "front_a", "trailer")]
                fields += [f"{word:08x}" for word in row["words"]]
                out.write("\t".join(fields) + "\n")
        print(f"wrote {args.dump}")

    if not args.words:
        args.words = True

    print("\nword summary (offset, distinct, constant value or relation to N)")
    for index in range(WORDS):
        values = Counter(row["words"][index] for row in rows)
        offset = 4 * index
        distinct = len(values)
        if distinct == 1:
            print(f"+0x{offset:02x}\t1\tconstant {next(iter(values)):08x}")
            continue
        text = f"+0x{offset:02x}\t{distinct}"
        counts = Counter(row["words"][index] for row in rows)
        top, hits = counts.most_common(1)[0]
        text += f"\ttop {top:08x} ({hits}/{len(rows)})"
        # Test simple relations against the parsed fields.
        relations = []
        for field in ("count", "mode", "version", "size_b", "front_a", "trailer"):
            if all(row["words"][index] == row[field] for row in rows):
                relations.append(f"=={field}")
        if all(row["words"][index] == align16(row["size_b"]) for row in rows):
            relations.append("==align16(size_b)")
        if all((row["words"][index] & 0xFFFF) == row["count"] for row in rows):
            relations.append("low16==N")
        if all((row["words"][index] >> 16) == row["count"] for row in rows):
            relations.append("high16==N")
        if relations:
            text += "\t" + ",".join(relations)
        print(text)

    # Mode low half versus the fitted Front B stride.
    print("\nmode low u16 by version (front B stride = size_b / count)")
    strides = defaultdict(Counter)
    for row in rows:
        low = row["mode"] & 0xFFFF
        stride = row["size_b"] / row["count"]
        strides[(low, row["version"])][round(stride, 3)] += 1
    print("low\tversion\theaders\ttop strides (value:count)")
    for (low, version), counts in sorted(strides.items(), key=lambda item: -sum(item[1].values())):
        top = ", ".join(f"{value}:{n}" for value, n in counts.most_common(5))
        print(f"{low}\t0x{version:08x}\t{sum(counts.values())}\t{top}")


if __name__ == "__main__":
    main()
