"""Probe the `CHKS` trailer that follows `LRSC` in `levels`-style records.

`script.rpf` records carry six chunks; records extracted from `levels.rpf` carry a
seventh, `CHKS`, whose payload is 12 bytes.  The first four bytes are a
**big-endian total record size** and match the decompressed body length in every
record measured.  The next four bytes are an unknown tag — not joaat32, not
crc32, not adler32, over the body, over the body prefix, or (tested here) over
the compressed stream.  The trailing `7a 70 70 70` is `0x70` memset filler.

    python3 tools/chks_probe.py --archive /path/levels.rpf --index output/index/levels.tsv
"""

import argparse
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import script_meta as sm


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


def murmur3_32(data, seed=0):
    mask = 0xFFFFFFFF
    c1, c2 = 0xCC9E2D51, 0x1B873593
    value = seed & mask
    length = len(data)
    for index in range(0, length - length % 4, 4):
        (block,) = struct.unpack_from("<I", data, index)
        block = (block * c1) & mask
        block = ((block << 15) | (block >> 17)) & mask
        block = (block * c2) & mask
        value ^= block
        value = ((value << 13) | (value >> 19)) & mask
        value = (value * 5 + 0xE6546B64) & mask
    tail = data[length - length % 4:]
    block = 0
    for index, byte in enumerate(tail):
        block |= byte << (index * 8)
    if tail:
        block = (block * c1) & mask
        block = ((block << 15) | (block >> 17)) & mask
        block = (block * c2) & mask
        value ^= block
    value ^= length
    value ^= value >> 16
    value = (value * 0x85EBCA6B) & mask
    value ^= value >> 13
    value = (value * 0xC2B2AE35) & mask
    value ^= value >> 16
    return value


def xxh32(data, seed=0):
    mask = 0xFFFFFFFF
    p1, p2, p3, p4, p5 = 0x9E3779B1, 0x85EBCA77, 0xC2B2AE3D, 0x27D4EB2F, 0x165667B1

    def rotl(value, count):
        return ((value << count) | (value >> (32 - count))) & mask

    length = len(data)
    index = 0
    if length >= 16:
        v1, v2, v3, v4 = (seed + p1 + p2) & mask, (seed + p2) & mask, seed & mask, (seed - p1) & mask
        while index <= length - 16:
            for name in range(4):
                (block,) = struct.unpack_from("<I", data, index)
                index += 4
                if name == 0:
                    v1 = (rotl((v1 + block * p2) & mask, 13) * p1) & mask
                elif name == 1:
                    v2 = (rotl((v2 + block * p2) & mask, 13) * p1) & mask
                elif name == 2:
                    v3 = (rotl((v3 + block * p2) & mask, 13) * p1) & mask
                else:
                    v4 = (rotl((v4 + block * p2) & mask, 13) * p1) & mask
        value = (rotl(v1, 1) + rotl(v2, 7) + rotl(v3, 12) + rotl(v4, 18)) & mask
    else:
        value = (seed + p5) & mask
    value = (value + length) & mask
    while index <= length - 4:
        (block,) = struct.unpack_from("<I", data, index)
        index += 4
        value = (value + block * p3) & mask
        value = (rotl(value, 17) * p4) & mask
    while index < length:
        value = (value + data[index] * p5) & mask
        value = (rotl(value, 11) * p1) & mask
        index += 1
    value ^= value >> 15
    value = (value * p2) & mask
    value ^= value >> 13
    value = (value * p3) & mask
    value ^= value >> 16
    return value


def fnv1a(data):
    value = 0x811C9DC5
    for byte in data:
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args()

    sm.MAGICS[b"CHKS"] = "CHKS"
    import csv
    ranges = sorted((int(row["start"], 16), int(row["end"], 16))
                    for row in csv.DictReader(args.index.open(), delimiter="\t")
                    if row["kind"] == "zlib")

    counters = {"records": 0, "with_chks": 0, "size_matches": 0}
    samples = []

    with args.archive.open("rb") as handle:
        for position, (start, end) in enumerate(ranges):
            handle.seek(start)
            raw = handle.read(end - start)
            try:
                body = zlib.decompress(raw)
            except zlib.error:
                continue
            if not body.startswith(b"PSIN"):
                continue
            if len(body) == 65536 and position + 1 < len(ranges):
                try:
                    nstart, nend = ranges[position + 1]
                    handle.seek(nstart)
                    body += zlib.decompress(handle.read(nend - nstart))
                except zlib.error:
                    pass
            counters["records"] += 1
            chunks = sm.walk(body)
            if not chunks or chunks[-1]["magic"] != "CHKS":
                continue
            counters["with_chks"] += 1
            offset = chunks[-1]["offset"]
            payload = body[offset + 8:offset + 8 + chunks[-1]["next"] - 8]
            if len(payload) < 8:
                continue
            size_be = struct.unpack_from(">I", payload, 0)[0]
            tag = payload[4:8]
            prefix = body[:offset]
            counters["size_matches"] += size_be == len(body)
            candidates = {
                "crc_body": zlib.crc32(body) & 0xFFFFFFFF,
                "crc_prefix": zlib.crc32(prefix) & 0xFFFFFFFF,
                "crc_compressed": zlib.crc32(raw) & 0xFFFFFFFF,
                "joaat_body": joaat(body),
                "joaat_compressed": joaat(raw),
                "fnv_body": fnv1a(body),
                "murmur3_body": murmur3_32(body),
                "murmur3_prefix": murmur3_32(prefix),
                "murmur3_compressed": murmur3_32(raw),
                "xxh32_body": xxh32(body),
                "xxh32_prefix": xxh32(prefix),
                "xxh32_compressed": xxh32(raw),
            }
            for name, value in candidates.items():
                counters.setdefault(name, 0)
                if struct.pack("<I", value) == tag or struct.pack(">I", value) == tag:
                    counters[name] += 1
            if len(samples) < 5:
                samples.append((position, len(body), len(raw), payload.hex(),
                                {k: hex(v) for k, v in candidates.items()}))
            if counters["with_chks"] >= args.limit:
                break

    for position, length, compressed, payload, candidates in samples:
        print(f"record {position}: body {length} compressed {compressed} chks {payload}")
        print(f"   {candidates}")
    print()
    for name, value in counters.items():
        print(f"{name:16s} {value}")


if __name__ == "__main__":
    raise SystemExit(main())
