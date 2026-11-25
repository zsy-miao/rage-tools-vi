"""Find and extract PSIN records in any archive, not just `script.rpf`.

`levels.rpf` turns out to carry 5,116 records with the same seven-section sequence
(`PSIN`/`LSCH`/`LENM`/`LSNS`/`LGID`/`LRSC`/`CHKS`) as the script archive, so the
script schema is not script-only. This sweeps an archive's streams for the `PSIN`
magic and dumps the property rows in the same format `tools/psin_extract.py` writes.

    python3 tools/psin_sweep.py --archive levels.rpf --index output/index/levels.tsv \\
        --out cache/psin-properties-levels.tsv --limit-mb 400000
"""
import argparse
import csv
import mmap
import struct
import zlib
from pathlib import Path

TYPES = {0x101, 0x102, 0x103, 0x104, 0x105}


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


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-decoded", type=int, default=400_000,
                        help="skip streams whose decoded size exceeds this")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    handle = args.archive.open("rb")
    data = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
    rows = sorted((int(r["start"], 16), int(r["end"], 16),
                   int(r["decoded_bytes"] or 0))
                  for r in csv.DictReader(args.index.open(), delimiter="\t")
                  if r["kind"] == "zlib")
    if args.limit:
        rows = rows[:args.limit]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    records = written = 0
    with args.out.open("w") as out:
        out.write("psin\toffset\tvalue\ttype\tclass_hash\tfield_hash\tas_float\n")
        for start, end, decoded in rows:
            if decoded > args.max_decoded:
                continue
            try:
                body = zlib.decompress(data[start:end])
            except zlib.error:
                continue
            if body[:4] != b"PSIN":
                continue
            records += 1
            for tag, offset, size in sections(body):
                if tag != "PSIN":
                    continue
                psin = body[offset + 8:offset + size]
                run = []
                for position in range(0, (len(psin) // 16) * 16, 16):
                    value, kind, prop, key = struct.unpack_from("<IIII", psin, position)
                    if kind in TYPES:
                        run.append((position, value, kind, prop, key))
                        continue
                    written += flush(out, f"{start:x}", run)
                    run = []
                written += flush(out, f"{start:x}", run)
    data.close()
    handle.close()
    print(f"{records} PSIN records, {written} rows -> {args.out}")
    return 0


def flush(out, record, run, minimum=4):
    if len(run) < minimum:
        return 0
    for position, value, kind, prop, key in run:
        value_float = struct.unpack("<f", struct.pack("<I", value))[0]
        out.write(f"{record}\t0x{position:x}\t0x{value:08x}\t0x{kind:03x}\t"
                  f"0x{prop:08x}\t0x{key:08x}\t{value_float:g}\n")
    return len(run)


if __name__ == "__main__":
    raise SystemExit(main())
