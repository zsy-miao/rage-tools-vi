"""Harvest the ASCII resource paths that `levels` PSIN sections carry.

Some PSIN sections in `levels` records store NUL-padded paths, for example
`acaidreams_protectedarea/all.pso.meta`. Those paths are literal text: they are a
name source that does not depend on the JOAAT name registry, and they can be
hashed and tested against every hash table we already have.

  python3 tools/levels_paths.py --archive $RAGE_SRC/levels.rpf \\
      --index output/index/levels.tsv --limit 2000 --out cache/levels-paths.txt
"""

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import script_meta as sm
import psin_blocks as pb

PATHLIKE = re.compile(rb"[A-Za-z0-9_./%:+-]{6,}")
EXTENSIONS = (b".pso", b".meta", b".gfx", b".dat", b".xml", b".ityp", b".ipl", b".blk")


def joaat(data, seed=0):
    value = seed & 0xFFFFFFFF
    for byte in data:
        value = (value + byte) & 0xFFFFFFFF
        value = (value + (value << 10)) & 0xFFFFFFFF
        value ^= value >> 6
    value = (value + (value << 3)) & 0xFFFFFFFF
    value ^= value >> 11
    value = (value + (value << 15)) & 0xFFFFFFFF
    return value & 0xFFFFFFFF


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--out", type=Path, help="write harvested paths here")
    parser.add_argument("--names", type=Path, default=Path("handoff/names.tsv"))
    args = parser.parse_args()

    known = set()
    if args.names.is_file():
        for row in csv.DictReader(args.names.open(), delimiter="\t"):
            try:
                known.add(int(row["hash"], 16))
            except (KeyError, ValueError):
                pass

    paths = Counter()
    per_tag = Counter()
    records = 0
    for record, body in sm.streams(args.archive, args.index):
        for tag, payload in pb.blocks(body):
            if b"/" not in payload:
                continue
            for match in PATHLIKE.findall(payload):
                if not any(match.lower().endswith(ext) for ext in EXTENSIONS):
                    continue
                paths[match] += 1
                per_tag[tag] += 1
        records += 1
        if args.limit and records >= args.limit:
            break

    print(f"records {records}  distinct paths {len(paths)}  occurrences {sum(paths.values())}")
    print("sections carrying paths:", [(hex(t), c) for t, c in per_tag.most_common(6)])

    hits = 0
    found = []
    for path, count in paths.items():
        stem = path.rsplit(b".", 1)[0]
        for form in (path, stem, b"platform:/levels/" + path, b"levels/" + path):
            value = joaat(form)
            if value in known:
                hits += 1
                found.append((path.decode("ascii", "replace"), known_value := hex(value)))
                break
    print(f"joaat hits in the name registry: {hits}")
    for path, value in found[:20]:
        print(f"   {value}  {path}")

    for path, count in paths.most_common(12):
        print(f"   x{count:<4d} {path.decode('ascii', 'replace')}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as handle:
            for path, count in paths.most_common():
                handle.write(f"{count}\t{path.decode('ascii', 'replace')}\n")
        print(f"\npaths -> {args.out}")


if __name__ == "__main__":
    raise SystemExit(main())
