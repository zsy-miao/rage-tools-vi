"""Probe the 208-byte plaintext descriptor that `core_bvh4` stores per entry.

Every `core_bvh4` entry begins with a zlib stream that decodes to exactly 208
bytes.  This tool samples those streams directly from the archive, reports the
per-field layout, and tests whether any field is a pack-relative offset, an
absolute offset, a size, or a small tagged index.  Those tests decide whether the
descriptor can be tied to the RPF9 entry table.
"""

import argparse
import csv
import mmap
import struct
import zlib
from collections import Counter
from pathlib import Path

SIZE = 208
WORDS = SIZE // 4


def f32(word):
    return struct.unpack("<f", struct.pack("<I", word))[0]


def basis_check(samples):
    """The three float3 rows at +0x50/+0x60/+0x70 should be a proper basis."""
    import math
    good = 0
    worst = 0.0
    positive = 0
    for _, words, _ in samples:
        rows = [tuple(f32(words[base + offset]) for offset in range(3))
                for base in (20, 24, 28)]
        a, b_, c = rows
        norms = [math.sqrt(sum(x * x for x in row)) for row in rows]
        dots = [sum(x * y for x, y in zip(a, b_)),
                sum(x * y for x, y in zip(a, c)),
                sum(x * y for x, y in zip(b_, c))]
        error = max(abs(n - 1) for n in norms + [0]) if False else max(
            [abs(n - 1) for n in norms] + [abs(d) for d in dots])
        worst = max(worst, error)
        if error < 1e-3:
            good += 1
        det = (a[0] * (b_[1] * c[2] - b_[2] * c[1])
               - a[1] * (b_[0] * c[2] - b_[2] * c[0])
               + a[2] * (b_[0] * c[1] - b_[1] * c[0]))
        if det > 0:
            positive += 1
    print(f"\nbasis at +0x50/+0x60/+0x70: orthonormal {good}/{len(samples)}, "
          f"det>0 {positive}/{len(samples)}, worst error {worst:.2e}")


def payload_check(samples, index_path):
    """+0xa0 should not exceed the following stream's decoded size."""
    rows = sorted((int(row["start"], 16), int(row["end"], 16), int(row["decoded_bytes"] or 0))
                  for row in csv.DictReader(index_path.open(), delimiter="\t")
                  if row["kind"] == "zlib")
    starts = [row[0] for row in rows]
    import bisect
    equal = less = greater = 0
    diffs = []
    for start, words, _ in samples:
        at = bisect.bisect_right(starts, start)
        if at >= len(rows):
            continue
        size = words[40]
        decoded = rows[at][2]
        if size == decoded:
            equal += 1
        elif size < decoded:
            less += 1
            diffs.append(decoded - size)
        else:
            greater += 1
    multiples = sum(1 for diff in diffs if diff % 256 == 0)
    print(f"+0xa0 vs next stream decoded: equal {equal}, smaller {less}, larger {greater}")
    print(f"  padding (next - +0xa0): {multiples}/{len(diffs)} are multiples of 256")


def verify_padding(samples, archive, index_path, count):
    """Confirm the bytes past +0xa0 inside a data stream are zero."""
    import random
    rows = sorted((int(row["start"], 16), int(row["end"], 16), int(row["decoded_bytes"] or 0))
                  for row in csv.DictReader(index_path.open(), delimiter="\t")
                  if row["kind"] == "zlib")
    starts = [row[0] for row in rows]
    import bisect
    candidates = []
    for start, words, _ in samples:
        at = bisect.bisect_right(starts, start)
        if at < len(rows) and words[40] < rows[at][2]:
            candidates.append((words[40], rows[at]))
    random.seed(7)
    picked = random.sample(candidates, min(count, len(candidates)))
    ok = bad = 0
    with archive.open("rb") as handle:
        mm = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        for size, stream in picked:
            try:
                data = zlib.decompress(mm[stream[0]:stream[1]])
            except zlib.error:
                continue
            tail = data[size:stream[2]]
            if tail and all(byte == 0 for byte in tail):
                ok += 1
            else:
                bad += 1
        mm.close()
    print(f"zero padding past +0xa0: {ok} ok, {bad} not zero of {len(picked)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path,
                        default=Path("/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK/pack/core_bvh4/core_bvh4.rpf"))
    parser.add_argument("--index", type=Path, default=Path("output/index/core_bvh4.tsv"))
    parser.add_argument("--census", type=Path, default=Path("handoff/header-census-full.tsv"))
    parser.add_argument("--sample", type=int, default=20000)
    parser.add_argument("--dump", type=int, default=3)
    parser.add_argument("--cache", type=Path, default=Path("cache/bvh4-descriptors.bin"),
                        help="decoded sample cache; written on first run")
    parser.add_argument("--verify-padding", type=int, default=0,
                        help="re-read this many data streams and check zero padding past +0xa0")
    parser.add_argument("--checks", action="store_true",
                        help="run the basis and payload-size checks")
    args = parser.parse_args()

    rows = []
    with args.index.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["kind"] == "zlib" and row["decoded_bytes"] == str(SIZE):
                rows.append((int(row["start"], 16), int(row["end"], 16)))
    rows.sort()
    total = len(rows)
    step = max(1, total // args.sample)
    sample = rows[::step][: args.sample]
    print(f"descriptor streams: {total}, sampled: {len(sample)} (every {step})")

    packs = []
    with args.census.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["archive"] != args.archive.name:
                continue
            packs.append((int(row["offset"], 16), int(row["count"])))
    packs.sort()
    print(f"packs in archive: {len(packs)}")

    fields = [Counter() for _ in range(WORDS)]
    samples = []
    if args.cache and args.cache.is_file():
        blob = args.cache.read_bytes()
        stride = SIZE + 8
        for index in range(len(blob) // stride):
            chunk = blob[index * stride:(index + 1) * stride]
            start = struct.unpack_from("<Q", chunk, 0)[0]
            data = chunk[8:]
            words = struct.unpack("<%dI" % WORDS, data)
            for at, word in enumerate(words):
                fields[at][word] += 1
            samples.append((start, words, data))
        print(f"loaded {len(samples)} descriptors from {args.cache}")
    else:
        with args.archive.open("rb") as handle:
            mm = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
            if hasattr(mm, "madvise"):
                try:
                    mm.madvise(mmap.MADV_RANDOM)
                except OSError:
                    pass
            for start, end in sample:
                try:
                    data = zlib.decompress(mm[start:end])
                except zlib.error:
                    continue
                if len(data) != SIZE:
                    continue
                words = struct.unpack("<%dI" % WORDS, data)
                for index, word in enumerate(words):
                    fields[index][word] += 1
                samples.append((start, words, data))
            mm.close()
        if args.cache and samples:
            with args.cache.open("wb") as out:
                for start, _, data in samples:
                    out.write(struct.pack("<Q", start) + data)
            print(f"cached {len(samples)} descriptors to {args.cache}")

    print(f"decoded: {len(samples)}")
    print("\nword layout (offset, distinct, zero%, min..max, top values)")
    for index, counter in enumerate(fields):
        values = sorted(counter)
        zeros = counter.get(0, 0) / len(samples)
        top = ", ".join(f"0x{v:08x}x{c}" for v, c in counter.most_common(3))
        print(f"  +0x{4 * index:03x} distinct={len(counter):>6} zero={zeros:>5.1%} "
              f"range=0x{values[0]:08x}..0x{values[-1]:08x}  {top}")

    # Tagged-pointer test: high nibble tags with a small low value.
    print("\n64-bit word tags (low half / high half)")
    for index in range(0, WORDS - 1, 2):
        low = Counter(words[index] for _, words, _ in samples)
        high = Counter(words[index + 1] for _, words, _ in samples)
        low_equal_zero = low.get(0, 0) / len(samples)
        print(f"  +0x{4 * index:03x}/+0x{4 * index + 4:03x}: low zero={low_equal_zero:>5.1%} "
              f"high top={', '.join(f'0x{v:08x}x{c}' for v, c in high.most_common(2))}")

    # Relation tests against offsets and sizes.
    print("\nrelation tests (fraction of samples where any word matches)")
    tests = {
        "absolute offset": lambda start, words, data: start in words,
        "offset >> 4": lambda start, words, data: (start >> 4) in words,
        "offset & 0xffff": lambda start, words, data: (start & 0xFFFF) in words,
        "low16 of offset in high16": lambda start, words, data: any((w >> 16) == (start & 0xFFFF) for w in words),
    }
    for label, test in tests.items():
        hits = sum(1 for start, words, data in samples if test(start, words, data))
        print(f"  {label:28s} {hits}/{len(samples)}")

    # Pack-relative delta: distance to the nearest preceding pack header.
    import bisect
    starts = [pack[0] for pack in packs]
    deltas = []
    for start, words, data in samples:
        at = bisect.bisect_right(starts, start) - 1
        if at < 0:
            continue
        delta = start - starts[at]
        deltas.append((delta, words, data))
    print(f"\npack-relative delta test on {len(deltas)} descriptors")
    for label, transform in (
        ("delta", lambda d: d),
        ("delta >> 4", lambda d: d >> 4),
        ("delta & 0xffff", lambda d: d & 0xFFFF),
    ):
        hits = sum(1 for delta, words, data in deltas if transform(delta) in words)
        print(f"  {label:16s} {hits}/{len(deltas)}")
    used = Counter()
    for delta, words, data in deltas:
        if delta in words:
            used[words.index(delta)] += 1
    print("  word positions matching delta:", dict(used.most_common(4)))

    if args.checks:
        basis_check(samples)
        payload_check(samples, args.index)
        if args.verify_padding:
            verify_padding(samples, args.archive, args.index, args.verify_padding)

    for start, words, data in samples[: args.dump]:
        print(f"\ndescriptor at 0x{start:x}")
        for at in range(0, SIZE, 16):
            print(f"  +0x{at:03x} {data[at:at + 16].hex(' ')}")


if __name__ == "__main__":
    main()
