"""Parse the LSNS section as what it is: a container of 16-byte-record tables.

The public GTA6 format notes describe `LSNS` as

    u32 table count N | 4 flag bytes | per table: u32 length (+ u32 id, except last)

with the header `8 + 4N + 4(N-1)` bytes, tables contiguous, every length a
multiple of 16, and `header + sum(lengths) == payload size`. That contradicts this
project's earlier reading of the section as an encrypted blob: the bytes are
high-entropy because the records are hashes, not because a cipher is involved.

This tool applies the framing, checks the arithmetic on every record, and reports
the table and record counts.

    python3 tools/lsns_tables.py --archive script.rpf --index output/index/script.tsv
"""
import argparse
import csv
import struct
import zlib
from collections import Counter
from pathlib import Path


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


def parse(payload):
    """Return (tables, flags) or None when the framing does not hold."""
    if len(payload) < 12:
        return None
    count = struct.unpack_from("<I", payload, 0)[0]
    if not 1 <= count <= 8:
        return None
    flags = payload[4:8]
    header = 8 + 4 * count + 4 * (count - 1)
    tables = []
    position = 8
    for index in range(count):
        if position + 4 > len(payload):
            return None
        length = struct.unpack_from("<I", payload, position)[0]
        position += 4
        if length % 16:
            return None
        tables.append((length, position))
        position += length
        if index != count - 1:
            position += 4          # table identifier
    if position != len(payload):
        return None
    if sum(length for length, _ in tables) + header != len(payload):
        return None
    return tables, flags


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive", type=Path, default=Path("script.rpf"))
    parser.add_argument("--index", type=Path, default=Path("output/index/script.tsv"))
    parser.add_argument("--show", type=int, default=0,
                        help="dump this many records of the first table found")
    args = parser.parse_args()

    rows = sorted((int(r["start"], 16), int(r["end"], 16))
                  for r in csv.DictReader(args.index.open(), delimiter="\t")
                  if r["kind"] == "zlib")
    data = args.archive.read_bytes()
    counts = Counter()
    records = Counter()
    tables_total = 0
    records_total = 0
    bad = 0
    seen = 0
    dumped = False
    position = 0
    while position < len(rows):
        start, end = rows[position]
        try:
            body = zlib.decompress(data[start:end])
        except zlib.error:
            position += 1
            continue
        if not body.startswith(b"PSIN"):
            position += 1
            continue
        if len(body) == 65536 and position + 1 < len(rows):
            nxt_start, nxt_end = rows[position + 1]
            try:
                body += zlib.decompress(data[nxt_start:nxt_end])
            except zlib.error:
                pass
        found = {tag: (offset, size) for tag, offset, size in sections(body)}
        if "LSNS" in found:
            offset, size = found["LSNS"]
            payload = body[offset + 8:offset + size]
            parsed = parse(payload)
            seen += 1
            if parsed is None:
                bad += 1
            else:
                tables, flags = parsed
                counts[len(tables)] += 1
                tables_total += len(tables)
                records_total += sum(length // 16 for length, _ in tables)
                for length, _ in tables:
                    records[length // 16] += 1
                if args.show and not dumped:
                    first_length, first_at = tables[0]
                    for index in range(min(args.show, first_length // 16)):
                        values = struct.unpack_from("<IIII", payload, first_at + 16 * index)
                        print(f"  rec {index:>4}: "
                              + " ".join(f"{v:08x}" for v in values))
                    dumped = True
        position += 1

    print(f"records with an LSNS section: {seen:,}; framing failed: {bad}")
    print(f"tables per record: {dict(counts.most_common())}")
    print(f"tables total: {tables_total:,}; 16-byte records total: {records_total:,}")
    print(f"records per table: {dict(records.most_common(6))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
