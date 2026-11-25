#!/usr/bin/env python3
"""Extract AWC containers (ADAT) from a raw audio span using mmap boundaries."""
import argparse
import csv
import hashlib
import mmap
import struct
import time
from pathlib import Path


def read_header(mm, pos):
    if mm[pos:pos+4] not in (b'ADAT', b'TADA'):
        return None
    version, flags = struct.unpack_from('<HH', mm, pos + 4)
    streams, data_offset = struct.unpack_from('<II', mm, pos + 8)
    if version != 1 or not (1 <= streams <= 1024) or not (16 <= data_offset <= 1 << 24):
        return None
    return version, flags, streams, data_offset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--start', type=lambda v: int(v, 0), required=True)
    parser.add_argument('--end', type=lambda v: int(v, 0), required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()

    rows = []
    started = time.monotonic()
    with args.archive.open('rb') as handle:
        mm = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        pos = args.start
        while pos < args.end:
            found = mm.find(b'ADAT', pos, args.end)
            if found < 0:
                break
            header = read_header(mm, found)
            if header is None:
                pos = found + 1
                continue
            version, flags, streams, data_offset = header
            nxt = mm.find(b'ADAT', found + 0x1000, args.end)
            end = nxt if nxt >= 0 else args.end
            if end <= found:
                pos = found + 1
                continue
            shard = args.out_dir / f'{found >> 24:02x}'
            shard.mkdir(parents=True, exist_ok=True)
            path = shard / f'{found:016x}.awc'
            payload = mm[found:end]
            path.write_bytes(payload)
            rows.append((found, end, end - found, version, flags, streams, data_offset, hashlib.sha256(payload).hexdigest(), str(path)))
            pos = end
            if args.limit and len(rows) >= args.limit:
                break
        mm.close()
    manifest = args.manifest or (args.out_dir / 'manifest.tsv')
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open('w', newline='') as handle:
        writer = csv.writer(handle, delimiter='\t', lineterminator='\n')
        writer.writerow(['start', 'end', 'bytes', 'version', 'flags', 'streams', 'data_offset', 'sha256', 'path'])
        for row in rows:
            writer.writerow([f'0x{row[0]:x}', f'0x{row[1]:x}', *row[2:]])
    print(f'awc={len(rows)} bytes={sum(row[2] for row in rows)} elapsed={time.monotonic()-started:.2f}s manifest={manifest}')


if __name__ == '__main__':
    main()
