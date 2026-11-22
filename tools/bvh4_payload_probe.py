"""Test the `core_bvh4` descriptor's sub-region fields against its payload.

The descriptor stores a u16 pair at `+0xa4`: the low half is always a multiple of
64 (the size of one node record) and the high half a multiple of 256 (the payload
header size).  If the pair describes internal spans, then

    nodes      = low  / 64
    blocks     = high / 256
    payload    = +0xa0

should be visible in the payload: a node table of `nodes` 64-byte records, a
bitmask run, and a primitive permutation whose length matches one of them.

For each sampled entry this tool decodes the payload, then reports the payload
size, the two u16 fields, the number of non-zero 64-byte records, the longest
run of `0x81` bytes, the longest small-integer permutation found in the body,
and the two `u64` header words.
"""

import argparse
import bisect
import csv
import mmap
import struct
import zlib
from collections import Counter
from pathlib import Path

SIZE = 208


def joaat(text):
    value = 0
    for byte in text.encode():
        value = (value + byte) & 0xFFFFFFFF
        value = (value + (value << 10)) & 0xFFFFFFFF
        value ^= value >> 6
    value = (value + (value << 3)) & 0xFFFFFFFF
    value ^= value >> 11
    value = (value + (value << 15)) & 0xFFFFFFFF
    return value & 0xFFFFFFFF


def longest_run(data, byte):
    best = run = 0
    for value in data:
        if value == byte:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def permutation_length(data, start, end):
    """Longest prefix of data[start:end] read as u32 that is a permutation of 0..n-1 or 1..n."""
    best = 0
    for offset in range(start, min(end, len(data)) - 8, 4):
        seen = set()
        for index in range(0, 4096, 4):
            at = offset + index
            if at + 4 > len(data):
                break
            value = struct.unpack_from("<I", data, at)[0]
            if value in seen or value > 4096:
                break
            seen.add(value)
        length = len(seen)
        if length > 1 and best < length:
            best = length
    return best


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path,
                        default=Path("/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK/pack/core_bvh4/core_bvh4.rpf"))
    parser.add_argument("--index", type=Path, default=Path("output/index/core_bvh4.tsv"))
    parser.add_argument("--cache", type=Path, default=Path("cache/bvh4-descriptors.bin"))
    parser.add_argument("--count", type=int, default=48)
    parser.add_argument("--tsv", type=Path, default=Path("cache/bvh4-payload-probe.tsv"))
    args = parser.parse_args()

    blob = args.cache.read_bytes()
    stride = SIZE + 8
    described = []
    for index in range(len(blob) // stride):
        chunk = blob[index * stride:(index + 1) * stride]
        described.append((struct.unpack_from("<Q", chunk, 0)[0],
                          struct.unpack("<%dI" % (SIZE // 4), chunk[8:])))
    streams = sorted((int(row["start"], 16), int(row["end"], 16), int(row["decoded_bytes"] or 0))
                     for row in csv.DictReader(args.index.open(), delimiter="\t")
                     if row["kind"] == "zlib")
    starts = [row[0] for row in streams]

    pairs = []
    for start, words in described:
        at = bisect.bisect_right(starts, start)
        if at < len(streams):
            pairs.append((start, words, streams[at]))
    step = max(1, len(pairs) // args.count)
    picked = pairs[::step][: args.count]

    print(f"{'desc':>12} {'a0':>8} {'lo/64':>6} {'hi/256':>6} {'h1':>8} {'h2':>8} "
          f"{'records':>7} {'msk':>4} {'perm':>5} {'perm/64':>7}")
    rows = []
    with args.archive.open("rb") as handle:
        mm = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        for start, words, stream in picked:
            try:
                data = zlib.decompress(mm[stream[0]:stream[1]])
            except zlib.error:
                continue
            size = words[40]
            data = data[:size]
            lo = words[41] & 0xFFFF
            hi = words[41] >> 16
            h1, h2 = struct.unpack_from("<QQ", data, 0x20)
            records = sum(1 for at in range(0x100, size, 64) if any(data[at:at + 64]))
            mask = longest_run(data, 0x81)
            perm = permutation_length(data, 0x100, min(size, 0x600))
            rows.append((start, size, lo, hi, h1, h2, records, mask, perm))
            print(f"0x{start:010x} {size:>8} {lo // 64:>6} {hi // 256:>6} {h1:>8} {h2:>8} "
                  f"{records:>7} {mask:>4} {perm:>5} {perm // 64 if perm else 0:>7}")
        mm.close()

    print("\nrelations across samples")
    for name, test in (
        ("records == lo/64", lambda e: e[6] == e[2] // 64),
        ("records == hi/256", lambda e: e[6] == e[3] // 256),
        ("perm == lo/64", lambda e: e[8] == e[2] // 64),
        ("perm == hi/256", lambda e: e[8] == e[3] // 256),
        ("h1 == a0", lambda e: e[4] == e[1]),
        ("h1 - h2 multiple of 256", lambda e: (e[4] - e[5]) % 256 == 0),
    ):
        hits = sum(1 for entry in rows if test(entry))
        print(f"  {name:26s} {hits}/{len(rows)}")

    print("\nmost common (records, perm):",
          Counter((entry[6] if entry[6] < 8 else ">=8",
                   entry[8] if entry[8] < 8 else ">=8") for entry in rows).most_common(6))


if __name__ == "__main__":
    main()
