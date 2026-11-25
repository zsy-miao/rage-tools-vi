"""Test the struct-first entry grammar on any archive, not just core_bvh4.

The grammar recovered from `core_bvh4` is:

    entry = [small struct][zero or more > 64 KiB streams]

where the struct starts 0x40 bytes of `0x5xxxxxxx`/`0x6xxxxxxx` tagged
self-relative pointers and a `{ptr, u16 count, u16 capacity}` array header.

This tool answers, per archive:

  1. how many streams are small (< 64 KiB) and how often a small stream is
     followed by one or more > 64 KiB streams (the "struct owns data" shape);
  2. for a decoded sample of small streams, how many carry the tagged-pointer
     signature, and how many of those are exactly 208 bytes;
  3. how far the resulting entry count is from each pack's declared N.

Everything except the sampled decodes is index-only, so it runs during an
extraction without competing for the archive.
"""

import argparse
import bisect
import csv
import mmap
import struct
import zlib
from collections import Counter
from pathlib import Path

SMALL = 65536
TAG_MASK = 0xF0000000


def load_pack_windows(census, archive):
    heads = sorted((int(row["offset"], 16), int(row["count"]), int(row["front_end"]))
                   for row in csv.DictReader(census.open(), delimiter="\t")
                   if row["archive"] == archive)
    return heads


def load_streams(index):
    return sorted((int(row["start"], 16), int(row["end"], 16), int(row["decoded_bytes"] or 0))
                  for row in csv.DictReader(index.open(), delimiter="\t")
                  if row["kind"] == "zlib")


def tagged_score(body):
    """Count tagged self-relative pointers in the first 0x40 bytes."""
    score = 0
    for offset in range(0, min(0x40, len(body) - 3), 4):
        value = struct.unpack_from("<I", body, offset)[0]
        if value >> 28 in (5, 6):
            target = value & 0x0FFFFFFF
            if target < len(body) or value >> 28 == 6:
                score += 1
    return score


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-name", default=None)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--census", type=Path, default=Path("handoff/header-census-full.tsv"))
    parser.add_argument("--sample", type=int, default=120)
    parser.add_argument("--tsv", type=Path, default=None)
    args = parser.parse_args()

    name = args.archive_name or args.archive.name
    windows = load_pack_windows(args.census, name)
    streams = load_streams(args.index)
    starts = [stream[0] for stream in streams]
    print(f"{name}: packs {len(windows)}, streams {len(streams)}")

    small = sum(1 for stream in streams if stream[2] < SMALL)
    empty = sum(1 for stream in streams if stream[2] == 0)
    print(f"  small (< 64 KiB): {small} ({small / len(streams):.1%}), empty: {empty}")

    followed = 0
    for stream, nxt in zip(streams, streams[1:]):
        if stream[2] < SMALL <= nxt[2]:
            followed += 1
    print(f"  small stream immediately followed by a >64 KiB stream: {followed}")

    # Entry count under the grammar: a small stream starts an entry, following
    # large streams attach to it. Packs are approximated by header windows.
    exact = short = long_ = 0
    residuals = Counter()
    for position, (head, count, _) in enumerate(windows):
        end = windows[position + 1][0] if position + 1 < len(windows) else 1 << 62
        low = bisect.bisect_left(starts, head)
        high = bisect.bisect_left(starts, end)
        window = streams[low:high]
        entries = 0
        open_entry = False
        for stream in window:
            if stream[2] < SMALL:
                entries += 1
                open_entry = True
            elif not open_entry:
                entries += 1
                open_entry = True
        delta = entries - count
        residuals[delta] += 1
        if delta == 0:
            exact += 1
        elif delta < 0:
            short += 1
        else:
            long_ += 1
    print(f"  packs matched by the grammar: {exact}/{len(windows)} "
          f"({exact / len(windows):.1%}), short {short}, long {long_}")
    print(f"  residual distribution (top): {residuals.most_common(6)}")

    # Signature sample: decode small streams spread across the archive.
    candidates = [stream for stream in streams if 16 <= stream[2] < 4096]
    if not candidates:
        print("  no small streams to sample")
        return
    step = max(1, len(candidates) // args.sample)
    picked = candidates[::step][: args.sample]
    hits = 0
    exact208 = 0
    per_size = Counter()
    rows = []
    with args.archive.open("rb") as handle:
        mm = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        if hasattr(mm, "madvise"):
            try:
                mm.madvise(mmap.MADV_RANDOM)
            except OSError:
                pass
        for stream in picked:
            try:
                body = zlib.decompress(mm[stream[0]:stream[1]])
            except zlib.error:
                continue
            score = tagged_score(body)
            if score >= 2:
                hits += 1
                per_size[len(body)] += 1
                if len(body) == 208:
                    exact208 += 1
                rows.append((stream[0], len(body), score))
        mm.close()
    print(f"  decoded {len(picked)} small streams: {hits} carry >=2 tagged pointers "
          f"({hits / max(1, len(picked)):.1%}), of which 208-byte: {exact208}")
    print(f"  struct sizes seen: {per_size.most_common(6)}")
    if args.tsv:
        args.tsv.parent.mkdir(parents=True, exist_ok=True)
        with args.tsv.open("w") as out:
            out.write("stream\tdecoded\ttagged\n")
            for row in rows:
                out.write(f"0x{row[0]:x}\t{row[1]}\t{row[2]}\n")
        print(f"  wrote {args.tsv}")


if __name__ == "__main__":
    main()
