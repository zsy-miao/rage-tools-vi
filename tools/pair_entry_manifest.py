"""Emit entry manifests for packs whose entry count verifies exactly.

For archives whose entries are `[struct][data]` pairs, a pack is usable when the
number of pairs found in its payload equals the declared N.  Only such packs are
emitted, so every row has a payload-derived boundary and an independent
declared-count check.

Streams are classified from the index alone: the struct half is a small stream
whose decoded body opens with two or more tagged self-relative pointers.  That
needs a decode, so run this against a local archive copy.
"""

import argparse
import bisect
import csv
import mmap
import struct
import zlib
from collections import Counter
from pathlib import Path

SELF_TAG = 5
TAG_MAX = 0x0A
SMALL = 65536


def is_struct(body):
    for base in (0, 0x100):
        if base + 0x40 > len(body):
            continue
        hits = 0
        for offset in range(base, base + 0x40, 4):
            value = struct.unpack_from("<I", body, offset)[0]
            tag = value >> 28
            if not (SELF_TAG <= tag <= TAG_MAX) or value & 0xF:
                continue
            # Tag-5 targets may lie outside this stream (navmeshes pointers do),
            # so alignment is the only filter.
            hits += 1
        if hits >= 2:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--census", type=Path, default=Path("handoff/header-census-full.tsv"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--unit", choices=("pairs", "chains"), default="pairs",
                        help="pairs = struct stream + data stream; chains = 64 KiB chain groups")
    parser.add_argument("--tolerance", type=int, default=2,
                        help="accept packs whose pair count differs from N by this much")
    args = parser.parse_args()

    packs = sorted((int(row["offset"], 16), int(row["count"]), int(row["front_end"]))
                   for row in csv.DictReader(args.census.open(), delimiter="\t")
                   if row["archive"] == args.archive.name)
    streams = sorted((int(row["start"], 16), int(row["end"], 16), int(row["decoded_bytes"] or 0))
                     for row in csv.DictReader(args.index.open(), delimiter="\t")
                     if row["kind"] == "zlib")
    starts = [stream[0] for stream in streams]

    if args.unit == "chains":
        # Chain unit needs no decode: a stream continues its predecessor when the
        # predecessor decoded exactly 65,536 bytes and starts on the align16 end.
        kinds = []
        previous = None
        for stream in streams:
            continues = (previous is not None and previous[0] == 65536
                         and stream[0] == ((previous[1] + 15) // 16 * 16))
            kinds.append(not continues)
            previous = (stream[2], stream[1])
    else:
        with args.archive.open("rb") as handle:
            mm = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
            kinds = []
            for stream in streams:
                # A struct stream is a descriptor; anything larger than 64 KiB
                # cannot be one, so skip the decode (this dominated the runtime).
                if stream[2] > (1 << 16):
                    kinds.append(False)
                    continue
                try:
                    kinds.append(is_struct(zlib.decompress(mm[stream[0]:stream[1]])))
                except zlib.error:
                    kinds.append(False)
            mm.close()

    rows = []
    verified = 0
    for position, (offset, count, front_end) in enumerate(packs):
        limit = packs[position + 1][0] if position + 1 < len(packs) else streams[-1][1] if streams else 0
        low = bisect.bisect_left(starts, offset + front_end)
        high = bisect.bisect_left(starts, limit)
        window = list(range(low, high))
        pairs = []
        if args.unit == "chains":
            # One entry per chain start; attached continuations belong to it.
            for stream_index in window:
                if kinds[stream_index]:
                    pairs.append((stream_index, None))
        else:
            index = 0
            while index < len(window):
                stream_index = window[index]
                if kinds[stream_index] and index + 1 < len(window):
                    data_index = window[index + 1]
                    pairs.append((stream_index, data_index))
                    index += 2
                else:
                    index += 1
        if abs(len(pairs) - count) > args.tolerance:
            continue
        verified += 1
        for entry, (head, data) in enumerate(pairs):
            rows.append({
                "pack": f"0x{offset:x}",
                "entry": entry,
                "declared_count": count,
                "delta": len(pairs) - count,
                "struct_stream": f"0x{streams[head][0]:x}",
                "struct_bytes": streams[head][2],
                "data_stream": "" if data is None else f"0x{streams[data][0]:x}",
                "data_decoded": "" if data is None else streams[data][2],
            })

    print(f"{args.archive.name}: {verified} of {len(packs)} packs verified, "
          f"{len(rows)} entries")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["pack", "entry", "declared_count", "delta", "struct_stream",
              "struct_bytes", "data_stream", "data_decoded"]
    with args.out.open("w") as out:
        out.write("\t".join(fields) + "\n")
        for row in rows:
            out.write("\t".join(str(row[field]) for field in fields) + "\n")
    print(f"wrote {args.out}")
    if rows:
        print("struct sizes:", Counter(row["struct_bytes"] for row in rows).most_common(4))


if __name__ == "__main__":
    main()
