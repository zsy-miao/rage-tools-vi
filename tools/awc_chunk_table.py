"""Locate and dump the AWC chunk table for every ADAT variant.

`0xff02` puts the table right after a `4 x streams` block, so its position is
computable. The older `0xff21` / `0xff61` containers do not: their table is simply
the 8-byte-aligned suffix that ends at `data_offset`, and the only way to find it
is to test candidate starts from the bottom up and keep the longest run of valid
records.

A record is `offset:28 | size:28 | type:8` little-endian, the same as `0xff02`,
so the per-stream chunks (`0x55` data, `0x76` descriptor, `0xa3`, `0x36`) have the
same meaning once the table is found.

    python3 tools/awc_chunk_table.py FILE [FILE ...]     # or --dir DIR --limit N
"""
import argparse
import struct
from collections import Counter
from pathlib import Path

KNOWN = {0x55, 0x36, 0x76, 0xA3, 0xFA, 0x48, 0x5C, 0x68, 0x2B, 0x5A, 0xD9, 0xBD}


def find_table(data):
    """Longest valid 8-byte-aligned chunk table ending at data_offset."""
    if len(data) < 16:
        return None
    streams, data_offset = struct.unpack_from("<II", data, 8)
    if not streams or not (16 < data_offset <= len(data)):
        return None
    best = None
    for start in range(16, data_offset):
        if (data_offset - start) % 8:
            continue
        chunks = []
        for position in range(start, data_offset, 8):
            raw = struct.unpack_from("<Q", data, position)[0]
            kind = raw >> 56
            size = (raw >> 28) & 0x0FFFFFFF
            offset = raw & 0x0FFFFFFF
            if kind not in KNOWN or not size or offset + size > len(data):
                chunks = []
                break
            chunks.append((kind, size, offset))
        if chunks and (best is None or len(chunks) > len(best[1])):
            best = (start, chunks)
    if best is None:
        return None
    return streams, data_offset, best[0], best[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*")
    parser.add_argument("--dir", type=Path)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    files = [Path(f) for f in args.files]
    if args.dir:
        files += sorted(args.dir.rglob("*.awc"))[:args.limit]
    for path in files:
        data = path.read_bytes()
        found = find_table(data)
        if not found:
            print(f"{path.name}: no chunk table")
            continue
        streams, data_offset, start, chunks = found
        kinds = Counter(kind for kind, _, _ in chunks)
        print(f"{path.name}: streams {streams}, table at 0x{start:x} "
              f"({len(chunks)} chunks, {len(chunks)/streams:.2f}/stream), "
              f"data at {data_offset}")
        print("   ", {hex(k): n for k, n in kinds.most_common()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
