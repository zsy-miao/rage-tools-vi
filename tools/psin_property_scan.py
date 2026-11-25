"""Does any archive besides `script.rpf` carry PSIN property arrays?

`script.rpf`'s PSIN directory points at blocks of 16-byte
`(value, type, property, key)` rows, with the type word restricted to
`0x101..0x105`. Other archives use different layouts, so a directory walk cannot
find their rows. This scans every byte offset of every PSIN body for runs of that
row shape and reports what it finds.

    python3 tools/psin_property_scan.py --archives archive:index.tsv ...
"""
import argparse
import mmap
import struct
import zlib
import csv
from pathlib import Path

TYPES = {0x101, 0x102, 0x103, 0x104, 0x105}


def scan(body, minimum=8):
    """Longest run of property rows at any 4-byte offset, as (rows, offset)."""
    best = (0, 0)
    limit = len(body) - 16 * minimum
    for start in range(0, max(0, limit), 4):
        run = 0
        position = start
        while position + 8 <= len(body):
            if struct.unpack_from("<I", body, position + 4)[0] not in TYPES:
                break
            run += 1
            position += 16
        if run > best[0]:
            best = (run, start)
    return best


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archives", nargs="+", required=True,
                        help="entries of the form path/to.rpf:output/index/name.tsv")
    parser.add_argument("--minimum", type=int, default=8)
    args = parser.parse_args()

    print(f"{'archive':26s} {'PSIN':>7} {'with rows':>10} {'rows':>9} {'longest':>8}")
    for spec in args.archives:
        archive, index = spec.split(":", 1)
        archive, index = Path(archive), Path(index)
        handle = archive.open("rb")
        data = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        rows = sorted((int(r["start"], 16), int(r["end"], 16),
                       int(r["decoded_bytes"] or 0))
                      for r in csv.DictReader(index.open(), delimiter="\t")
                      if r["kind"] == "zlib")
        records = with_rows = total = longest = 0
        for start, end, decoded in rows:
            if decoded > 400_000:
                continue
            try:
                body = zlib.decompress(data[start:end])
            except zlib.error:
                continue
            if body[:4] != b"PSIN":
                continue
            records += 1
            found, _ = scan(body, args.minimum)
            if found >= args.minimum:
                with_rows += 1
                total += found
                longest = max(longest, found)
        data.close()
        handle.close()
        print(f"{archive.name:26s} {records:>7,} {with_rows:>10,} {total:>9,} {longest:>8,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
