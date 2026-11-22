"""Probe `core_bvh4` payload internals: tail alignment, 0x81 runs, and +0xa4.

Three checks the corpus can answer without a full parse:

1. Tail rule: the payload's used size at `+0x20` should end on a 4-byte boundary
   if the final record is a 4-byte value, and the last non-zero byte sits three
   bytes before it in every sample so far.
2. `0x81` sentinel: quantized BVH nodes often fill unused int8 child boxes with
   min = +127 and max = -127 (0x81). If so, `0x81` and `0x7F` should occupy fixed
   offsets inside 64-byte records; if it is noise, their offsets are uniform.
3. `+0xa4`: the two u16 fields do not read as payload offsets. Partition the
   sample by `hi == 0` and correlate `lo`/`hi` with the payload header words.

Payloads are decoded once and cached, so repeated runs are offline.
"""

import argparse
import bisect
import csv
import mmap
import struct
import zlib
from collections import Counter, defaultdict
from pathlib import Path

DESCRIPTOR = 208


def load_descriptors(path):
    blob = path.read_bytes()
    stride = DESCRIPTOR + 8
    out = []
    for index in range(len(blob) // stride):
        chunk = blob[index * stride:(index + 1) * stride]
        out.append((struct.unpack_from("<Q", chunk, 0)[0],
                    struct.unpack("<%dI" % (DESCRIPTOR // 4), chunk[8:])))
    return out


def load_streams(path):
    return sorted((int(row["start"], 16), int(row["end"], 16), int(row["decoded_bytes"] or 0))
                  for row in csv.DictReader(path.open(), delimiter="\t")
                  if row["kind"] == "zlib")


def load_payloads(cache, archive, descriptors, streams, count):
    if cache.is_file():
        blob = cache.read_bytes()
        out = []
        at = 0
        while at + 12 <= len(blob):
            start, size = struct.unpack_from("<QI", blob, at)
            at += 12
            out.append((start, size, blob[at:at + size]))
            at += size
        print(f"loaded {len(out)} payloads from {cache}")
        return out

    starts = [row[0] for row in streams]
    pairs = []
    for start, words in descriptors:
        index = bisect.bisect_right(starts, start)
        if index < len(streams):
            pairs.append((start, words, streams[index]))
    step = max(1, len(pairs) // count)
    picked = pairs[::step][:count]

    out = []
    with archive.open("rb") as handle:
        mm = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        for start, words, stream in picked:
            try:
                data = zlib.decompress(mm[stream[0]:stream[1]])
            except zlib.error:
                continue
            size = words[40]
            out.append((start, size, data[:size]))
        mm.close()
    with cache.open("wb") as handle:
        for start, size, data in out:
            handle.write(struct.pack("<QI", start, len(data)) + data)
    print(f"cached {len(out)} payloads to {cache}")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path,
                        default=Path("/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK/pack/core_bvh4/core_bvh4.rpf"))
    parser.add_argument("--index", type=Path, default=Path("output/index/core_bvh4.tsv"))
    parser.add_argument("--descriptors", type=Path, default=Path("cache/bvh4-descriptors.bin"))
    parser.add_argument("--payload-cache", type=Path, default=Path("cache/bvh4-payloads.bin"))
    parser.add_argument("--count", type=int, default=200)
    args = parser.parse_args()

    described = load_descriptors(args.descriptors)
    streams = load_streams(args.index)
    payloads = load_payloads(args.payload_cache, args.archive, described, streams, args.count)
    words = {start: word for start, word in described}

    print("\n--- check 1: tail alignment ---")
    mod4 = Counter()
    tail = Counter()
    header = Counter()
    for start, size, data in payloads:
        h1, h2 = struct.unpack_from("<QQ", data, 0x20)
        nonzero = [i for i, value in enumerate(data) if value]
        last = nonzero[-1] + 1 if nonzero else 0
        mod4[h1 % 4] += 1
        tail[h1 - last] += 1
        header[(h2 == h1 - 256)] += 1
        if h1 > size or h1 < 0:
            print(f"  WARNING h1 {h1} outside payload {size} at 0x{start:x}")
    print(f"  +0x20 mod 4: {dict(mod4)}")
    print(f"  used - last_nonzero: {dict(tail)}")
    print(f"  h2 == h1 - 256: {dict(header)}")

    print("\n--- check 2: 0x81 / 0x7F sentinel ---")
    offset_81 = Counter()
    offset_7f = Counter()
    paired = 0
    runs = Counter()
    for start, size, data in payloads:
        body = data[0x100:struct.unpack_from("<Q", data, 0x20)[0]]
        for index, value in enumerate(body):
            if value == 0x81:
                offset_81[index % 64] += 1
            elif value == 0x7F:
                offset_7f[index % 64] += 1
        for index, value in enumerate(body):
            if value == 0x81:
                window = body[index:index + 64]
                if 0x7F in window:
                    paired += 1
        best = run = 0
        for value in body:
            run = run + 1 if value == 0x81 else 0
            best = max(best, run)
        runs[best] += 1
    total_81 = sum(offset_81.values())
    print(f"  0x81 bytes: {total_81}, 0x7F bytes: {sum(offset_7f.values())}")
    print(f"  0x81 with a 0x7F within 64 bytes: {paired}")
    print(f"  top 0x81 offsets in the 64-byte frame: {offset_81.most_common(6)}")
    print(f"  top 0x7F offsets in the 64-byte frame: {offset_7f.most_common(6)}")
    print(f"  longest 0x81 run: {sorted(runs.items())[-6:]}")

    print("\n--- check 3: +0xa4 against header fields ---")
    groups = defaultdict(list)
    for start, size, data in payloads:
        low = words[start][41] & 0xFFFF
        high = words[start][41] >> 16
        h1, h2 = struct.unpack_from("<QQ", data, 0x20)
        head = struct.unpack_from("<8I", data, 0)
        nonzero = [i for i, value in enumerate(data) if value]
        last = nonzero[-1] + 1 if nonzero else 0
        run = best = 0
        for value in data[0x100:max(last, 0x100)]:
            run = run + 1 if value == 0x81 else 0
            best = max(best, run)
        groups["hi=0" if high == 0 else "hi>0"].append((low, high, size, h1, last, head, best))

    for name, rows in groups.items():
        print(f"  {name}: {len(rows)} payloads")
        if not rows:
            continue
        size = sorted(row[2] for row in rows)
        run = sorted(row[6] for row in rows)
        print(f"    payload size: min {size[0]} median {size[len(size)//2]} max {size[-1]}")
        print(f"    longest 0x81 run: min {run[0]} median {run[len(run)//2]} max {run[-1]}")
        zeros = Counter(sum(1 for value in row[5] if value) for row in rows)
        print(f"    non-zero header words (first 32 bytes): {dict(zeros)}")
        lows = Counter(row[0] // 64 for row in rows)
        print(f"    lo/64 top: {lows.most_common(4)}")


if __name__ == "__main__":
    main()
