#!/usr/bin/env python3
"""Inspect GTA VI ADAT/AWC stream framing without decoding.

The GTA VI container differs from GTA V AWC: its header is 16-bit version/flags,
the stream index is u16 at 0x10, and the chunk table starts at 0x50.  This tool
records the 0x76 descriptor, 0x55 data size, and repeated `a0 00 f8` markers so
packet-boundary hypotheses can be tested against the whole corpus.
"""
from __future__ import annotations

import argparse
import csv
import mmap
import struct
from collections import Counter
from pathlib import Path

KNOWN = {0x55, 0x36, 0x76, 0xA3, 0xFA, 0x48, 0x5C, 0x68, 0x2B, 0x5A, 0xD9, 0xBD}
MARKER = b"\xa0\x00\xf8"
DEFAULT_MANIFEST = Path("output/extracted/audio-awc/manifest.tsv")
DEFAULT_OUT = Path("handoff/audio-awc-framing.tsv")


def parse_chunk_table(mm: mmap.mmap, start: int, data_offset: int):
    chunks = []
    if start < 0 or start >= data_offset or (data_offset - start) % 8:
        return []
    for pos in range(start, data_offset, 8):
        raw = struct.unpack_from("<Q", mm, pos)[0]
        typ = raw >> 56
        size = (raw >> 28) & 0x0FFFFFFF
        off = raw & 0x0FFFFFFF
        if typ not in KNOWN or not size or off + size > len(mm):
            return []
        chunks.append((typ, size, off))
    return chunks if any(t == 0x55 for t, _, _ in chunks) else []


def find_chunks(mm: mmap.mmap, data_offset: int):
    """The GTA VI table starts at 0x50; fall back to a validated suffix."""
    chunks = parse_chunk_table(mm, 0x50, data_offset)
    if chunks:
        return chunks
    for n in range(1, min(40000, data_offset // 8) + 1):
        chunks = parse_chunk_table(mm, data_offset - 8 * n, data_offset)
        if chunks:
            return chunks
    return []


def parse_awc(path: Path):
    with path.open("rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            if mm[:4] != b"ADAT":
                return []
            version, flags, streams = struct.unpack_from("<HHH", mm, 4)
            data_offset = struct.unpack_from("<I", mm, 0x0C)[0]
            if not streams or data_offset > len(mm):
                return []
            indexes = struct.unpack_from(f"<{streams}H", mm, 0x10)
            chunks = find_chunks(mm, data_offset)
            rows = []
            for stream in range(streams):
                start = indexes[stream]
                end = indexes[stream + 1] if stream + 1 < streams else len(chunks)
                data = next((mm[o:o+s] for t, s, o in chunks[start:end] if t == 0x55), None)
                fmt = next((mm[o:o+s] for t, s, o in chunks[start:end] if t == 0x76), None)
                if not data or not fmt or len(fmt) < 0x20:
                    continue
                num0 = struct.unpack_from("<I", fmt, 0x00)[0]
                rate = struct.unpack_from("<H", fmt, 0x08)[0]
                unk0a = struct.unpack_from("<H", fmt, 0x0A)[0]
                num1 = struct.unpack_from("<I", fmt, 0x0C)[0]
                codec = fmt[0x1C]
                subcodec = fmt[0x1D]
                ver = struct.unpack_from("<H", fmt, 0x1E)[0]
                positions = []
                pos = data.find(MARKER)
                while pos >= 0 and len(positions) < 16:
                    positions.append(pos)
                    pos = data.find(MARKER, pos + 1)
                rows.append({
                    "path": str(path),
                    "version": version,
                    "flags": f"0x{flags:04x}",
                    "streams": streams,
                    "data_offset": data_offset,
                    "stream": stream,
                    "num0": num0,
                    "rate": rate,
                    "unk0a": f"0x{unk0a:04x}",
                    "num1": num1,
                    "codec": f"0x{codec:02x}",
                    "subcodec": f"0x{subcodec:02x}",
                    "ver76": ver,
                    "data_size": len(data),
                    "marker_count": len(positions),
                    "marker_positions": ",".join(str(p) for p in positions),
                    "marker_gaps": ",".join(str(b - a) for a, b in zip(positions, positions[1:])),
                })
            return rows
        finally:
            mm.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int, default=500, help="0 = all containers")
    args = ap.parse_args()

    containers = list(csv.DictReader(args.manifest.open(), delimiter="\t"))
    if args.limit:
        containers = containers[: args.limit]
    rows = []
    for i, container in enumerate(containers, 1):
        try:
            rows.extend(parse_awc(Path(container["path"])))
        except Exception as exc:  # keep scanning; report the bad container
            rows.append({"path": container["path"], "error": str(exc)})
        if i % 100 == 0:
            print(f"scanned {i}/{len(containers)} containers, {len(rows)} streams")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["path", "version", "flags", "streams", "data_offset", "stream",
              "num0", "rate", "unk0a", "num1", "codec", "subcodec", "ver76",
              "data_size", "marker_count", "marker_positions", "marker_gaps", "error"]
    with args.out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    good = [r for r in rows if "error" not in r]
    print(f"wrote {len(rows)} rows -> {args.out}")
    print("codecs", Counter(r["codec"] for r in good))
    print("rates", Counter(r["rate"] for r in good))
    print("data sizes", Counter(r["data_size"] for r in good))
    print("marker counts", Counter(r["marker_count"] for r in good))
    print("first marker gaps", Counter(r["marker_gaps"] for r in good).most_common(10))
    print("subcodecs", Counter(r["subcodec"] for r in good))


if __name__ == "__main__":
    main()
