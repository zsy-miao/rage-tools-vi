"""Extract the PSIN property arrays straight from script.rpf.

Everything else in the PSIN toolchain reads `cache/psin-properties.tsv`. This is
the tool that produces it, so a fresh clone with the archive can go from
`script.rpf` to a readable schema in one command:

    python3 tools/psin_extract.py script.rpf --out cache/psin-properties.tsv

Records are 16 bytes: `u32 value, u32 type, u32 property, u32 key`, with the type
word restricted to `0x101..0x105`. Robustness comes from scanning every
record-aligned position and keeping maximal runs of at least four valid rows,
because the PSIN block directory does not align with record boundaries at the
end of a block.
"""
import argparse
import struct
import sys
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


def streams(archive, index):
    data = archive.read_bytes()
    rows = sorted((int(r["start"], 16), int(r["end"], 16))
                  for r in _rows(index) if r["kind"] == "zlib")
    position = 0
    while position < len(rows):
        start, end = rows[position]
        body = None
        try:
            body = zlib.decompress(data[start:end])
        except zlib.error:
            position += 1
            continue
        if body.startswith(b"PSIN"):
            # A record whose PSIN section is exactly one stream page continues
            # in the next stream.
            if len(body) == 65536 and position + 1 < len(rows):
                nxt_start, nxt_end = rows[position + 1]
                try:
                    body += zlib.decompress(data[nxt_start:nxt_end])
                except zlib.error:
                    pass
            yield position, body
        position += 1


def _rows(index):
    import csv
    with index.open() as handle:
        yield from csv.DictReader(handle, delimiter="\t")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--index", type=Path, default=Path("output/index/script.tsv"))
    parser.add_argument("--out", type=Path, default=Path("cache/psin-properties.tsv"))
    parser.add_argument("--minimum-run", type=int, default=4)
    args = parser.parse_args()

    if not args.archive.is_file():
        sys.exit(f"missing archive {args.archive}")
    if not args.index.is_file():
        sys.exit(f"missing index {args.index}; run tools/stream_index.py first")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with args.out.open("w") as out:
        # column names match the rest of the PSIN toolchain
        out.write("psin\toffset\tvalue\ttype\tclass_hash\tfield_hash\tas_float\n")
        for record, body in streams(args.archive, args.index):
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
                    written += _flush(out, record, run, args.minimum_run)
                    run = []
                written += _flush(out, record, run, args.minimum_run)
    print(f"{written} rows -> {args.out}")
    return 0


def _flush(out, record, run, minimum):
    if len(run) < minimum:
        return 0
    for position, value, kind, prop, key in run:
        value_float = struct.unpack("<f", struct.pack("<I", value))[0]
        out.write(f"{record}\t0x{position:x}\t0x{value:08x}\t0x{kind:03x}\t"
                  f"0x{prop:08x}\t0x{key:08x}\t{value_float:g}\n")
    return len(run)


if __name__ == "__main__":
    raise SystemExit(main())
