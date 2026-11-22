"""Resolve RPF9 pack extents from zero padding, in index-only mode.

Two signals, no payload decoding:

* **Zero padding.** Every header after the root is preceded by a contiguous
  zero run, so the pack immediately before a header ends at
  `header - padding`.  That boundary is exact for the last sibling.
* **Chains and the declared count.** A 64 KiB chain is the entry unit: a stream
  continues its predecessor when the predecessor decoded exactly 65,536 bytes
  and this stream starts on the align16 boundary of its end.  A header event
  closes every saturated pack under it; a pack is saturated when its direct
  items (chains plus child packs) reach its declared N, or when it holds no
  chains at all (a pure directory pack).

Because chains come from the index, this runs on the read-only volume while an
extraction is busy.
"""

import argparse
import bisect
import csv
from collections import Counter
from pathlib import Path

CHUNK = 65536


def align16(value):
    return (value + 15) // 16 * 16


def load_packs(census, archive):
    return sorted((int(row["offset"], 16), int(row["count"]), int(row["front_end"]),
                   int(row["trailer"]))
                  for row in csv.DictReader(census.open(), delimiter="\t")
                  if row["archive"] == archive)


def load_streams(index):
    return sorted((int(row["start"], 16), int(row["end"], 16), int(row["decoded_bytes"] or 0))
                  for row in csv.DictReader(index.open(), delimiter="\t")
                  if row["kind"] == "zlib")


def padding_before(mm, offset, maximum=1 << 20):
    run = 0
    position = offset - 1
    while position >= 0 and run < maximum and mm[position] == 0:
        run += 1
        position -= 1
    return run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--census", type=Path, default=Path("handoff/header-census-full.tsv"))
    parser.add_argument("--tsv", type=Path, default=None)
    parser.add_argument("--dp", action="store_true",
                        help="choose each pack end by minimising |items - N| over "
                             "the padding candidates, with children excluded")
    parser.add_argument("--leaves-only", action="store_true",
                        help="report only packs whose own window resolves exactly")
    parser.add_argument("--unit", choices=("chains", "structs"), default="chains",
                        help="entry unit: 64 KiB chains (index only) or decoded "
                             "struct roots (needs the payload)")
    args = parser.parse_args()

    packs = load_packs(args.census, args.archive.name)
    streams = load_streams(args.index)
    starts = [stream[0] for stream in streams]

    if args.unit == "structs":
        # Struct mode decodes each stream; use it on a local archive copy.
        import mmap as _mmap
        import struct as _struct
        import zlib as _zlib

        def is_struct(body):
            for base in (0, 0x100):
                if base + 0x40 > len(body):
                    continue
                hits = 0
                for offset in range(base, base + 0x40, 4):
                    value = _struct.unpack_from("<I", body, offset)[0]
                    tag = value >> 28
                    if not (5 <= tag <= 0x0A) or value & 0xF:
                        continue
                    target = value & 0x0FFFFFFF
                    if tag == 5 and not (base <= target < len(body)):
                        continue
                    hits += 1
                if hits >= 2:
                    return True
            return False

        with args.archive.open("rb") as handle:
            mm = _mmap.mmap(handle.fileno(), 0, access=_mmap.ACCESS_READ)
            chain_of = []
            for stream in streams:
                try:
                    chain_of.append(0 if is_struct(_zlib.decompress(mm[stream[0]:stream[1]])) else -1)
                except _zlib.error:
                    chain_of.append(-1)
            mm.close()
        # Struct mode: each struct is its own item; non-structs are ignored.
        chain_of = [index if value == 0 else -1 - index
                    for index, value in enumerate(chain_of)]
        chain_starts = [stream[0] for stream, value in zip(streams, chain_of) if value >= 0]
    # Chain grouping, index only.
    if args.unit == "chains":
        chain_of = []
        chain_starts = []
        previous = None
        for stream in streams:
            continues = (previous is not None and previous[0] == CHUNK
                         and stream[0] == align16(previous[1]))
            if not continues:
                chain_starts.append(stream[0])
            chain_of.append(len(chain_starts) - 1)
            previous = (stream[2], stream[1])

    print(f"{args.archive.name}: packs {len(packs)}, streams {len(streams)}, "
          f"chains {len(chain_starts)}")

    with args.archive.open("rb") as handle:
        import mmap
        mm = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        size = len(mm)

        events = [(row[0], 0, index) for index, row in enumerate(packs)]
        events.extend((stream[0], 1, index) for index, stream in enumerate(streams))
        events.sort()
        header_bounds = [packs[index + 1][0] if index + 1 < len(packs) else size
                         for index in range(len(packs))]

        stack = []
        resolved = {}

        def close(pack, boundary):
            own = align16(pack["last_end"]) + pack["trailer"]
            end = min(max(own, pack["front_end_abs"] + pack["trailer"]), boundary)
            pack["end"] = end
            resolved[pack["offset"]] = pack
            parent = pack.get("parent")
            if parent is not None:
                parent["last_end"] = max(parent["last_end"], end)

        for position, (offset, kind, index) in enumerate(events):
            if kind == 0:
                boundary = header_bounds[index]
                low = bisect.bisect_left(starts, offset + packs[index][2])
                high = bisect.bisect_left(starts, boundary)
                window_chains = len({chain_of[k] for k in range(low, high) if chain_of[k] >= 0})
                while stack:
                    top = stack[-1]
                    saturated = top["direct"] >= top["count"]
                    if saturated:
                        close(top, offset - padding_before(mm, offset))
                        stack.pop()
                    else:
                        break
                pack = {
                    "offset": offset, "count": packs[index][1],
                    "trailer": packs[index][3],
                    "front_end_abs": offset + packs[index][2],
                    "items": 0, "children": 0, "direct": 0,
                    "last_end": offset + packs[index][2], "seen": set(),
                }
                if stack:
                    stack[-1]["children"] += 1
                    stack[-1]["direct"] += 1
                    pack["parent"] = stack[-1]
                stack.append(pack)
            else:
                if not stack:
                    continue
                pack = stack[-1]
                key = chain_of[index]
                if key < 0:
                    continue
                if key not in pack["seen"]:
                    pack["seen"].add(key)
                    pack["items"] += 1
                    pack["direct"] += 1
                pack["last_end"] = max(pack["last_end"], streams[index][1])

        for pack in reversed(stack):
            close(pack, size)
        mm.close()

    if args.dp:
        import mmap as _mmap
        handle = args.archive.open("rb")
        mm = _mmap.mmap(handle.fileno(), 0, access=_mmap.ACCESS_READ)
        size = len(mm)
        # Candidate boundaries: the physical boundary before every header, plus
        # the file end.  Ends are chosen in reverse offset order so a pack's
        # children are already resolved and their payloads can be excluded.
        bounds = [0] * len(packs)
        for index in range(1, len(packs)):
            bounds[index] = packs[index][0] - padding_before(mm, packs[index][0])
        bounds[0] = 0
        ends = [size] * len(packs)
        scores = [None] * len(packs)
        fronts = [row[0] + row[2] for row in packs]

        def units_between(low, high):
            lo = bisect.bisect_left(starts, low)
            hi = bisect.bisect_left(starts, high)
            return len({chain_of[k] for k in range(lo, hi) if chain_of[k] >= 0})

        for i in range(len(packs) - 1, -1, -1):
            offset, count, front_end, trailer = packs[i]
            start = fronts[i]
            best = None
            for j in range(i + 1, len(packs) + 1):
                end = bounds[j] if j < len(packs) else size
                if end <= start + trailer:
                    continue
                stop = end - trailer
                children = 0
                cursor = i + 1
                ok = True
                while cursor < len(packs) and packs[cursor][0] < end:
                    if ends[cursor] > stop:
                        ok = False
                        break
                    children += 1
                    cursor += 1
                if not ok:
                    continue
                units = units_between(start, stop)
                for k in range(i + 1, cursor):
                    units -= units_between(fronts[k], max(fronts[k], ends[k] - packs[k][3]))
                score = abs(units + children - count)
                candidate = (score, end, units, children)
                if best is None or candidate < best:
                    best = candidate
            if best is None:
                best = (abs(count), size, 0, 0)
            scores[i] = best[0]
            ends[i] = best[1]
        mm.close()
        handle.close()

        aligned = sum(1 for end in ends if end % 16 == 0)
        exact = sum(1 for score in scores if score == 0)
        print(f"  DP ends: {len(ends)} packs, exact score {exact} "
              f"({exact / len(ends):.1%}), 16-aligned {aligned}/{len(ends)}")
        print(f"  score distribution: {Counter(scores).most_common(8)}")
        print(f"  bytes covered by exact packs: "
              f"{sum(ends[i] - packs[i][0] for i in range(len(packs)) if scores[i] == 0):,}")
        print(f"\n{'pack':>12} {'N':>5} {'end':>12} {'score':>6}")
        for i in range(min(16, len(packs))):
            print(f"0x{packs[i][0]:010x} {packs[i][1]:>5} 0x{ends[i]:010x} {scores[i]:>6}")
        if args.tsv:
            args.tsv.parent.mkdir(parents=True, exist_ok=True)
            with args.tsv.open("w") as out:
                out.write("archive\toffset\tcount\tend\tscore\n")
                for i in range(len(packs)):
                    out.write(f"{args.archive.name}\t0x{packs[i][0]:x}\t{packs[i][1]}\t"
                              f"0x{ends[i]:x}\t{scores[i]}\n")
            print(f"wrote {args.tsv}")
        return

    if args.leaves_only:
        import mmap as _mmap
        handle = args.archive.open("rb")
        mm = _mmap.mmap(handle.fileno(), 0, access=_mmap.ACCESS_READ)
        size = len(mm)
        # Exact leaf resolution: a pack is a leaf when the units in its own
        # window (front_end .. next_header - padding - trailer) equal N.  Its
        # end is then the physical boundary, which is independent of the tree.
        leaf_rows = []
        covered = 0
        for index, (offset, count, front_end, trailer) in enumerate(packs):
            limit = (packs[index + 1][0] - padding_before(mm, packs[index + 1][0])
                     if index + 1 < len(packs) else size)
            start = offset + front_end
            stop = max(start, limit - trailer)
            low = bisect.bisect_left(starts, start)
            high = bisect.bisect_left(starts, stop)
            units = len({chain_of[k] for k in range(low, high) if chain_of[k] >= 0})
            ok = units == count
            if ok:
                covered += limit - offset
            leaf_rows.append((offset, count, units, limit, ok))
        exact = sum(1 for row in leaf_rows if row[4])
        print(f"  exact leaves: {exact}/{len(leaf_rows)} "
              f"({exact / len(leaf_rows):.1%}), bytes covered {covered:,} "
              f"of {size:,} ({covered / size:.1%})")
        print(f"\n{'pack':>12} {'N':>5} {'units':>6} {'end':>12} ok")
        for row in leaf_rows:
            print(f"0x{row[0]:010x} {row[1]:>5} {row[2]:>6} 0x{row[3]:010x} "
                  f"{'yes' if row[4] else ''}")
        if args.tsv:
            args.tsv.parent.mkdir(parents=True, exist_ok=True)
            with args.tsv.open("w") as out:
                out.write("archive\toffset\tcount\tunits\tend\texact_leaf\n")
                for row in leaf_rows:
                    out.write(f"{args.archive.name}\t0x{row[0]:x}\t{row[1]}\t{row[2]}\t"
                              f"0x{row[3]:x}\t{int(row[4])}\n")
            print(f"wrote {args.tsv}")
        mm.close()
        handle.close()
        return

    rows = []
    for offset in sorted(resolved):
        pack = resolved[offset]
        rows.append((offset, pack["count"], pack["items"], pack["children"],
                     pack["direct"], pack["end"], int(pack["direct"] == pack["count"])))
    exact = sum(row[6] for row in rows)
    print(f"  packs resolved: {len(rows)}, count satisfied: {exact} ({exact / len(rows):.1%})")
    print(f"  residual (N - direct): "
          f"{Counter(row[1] - row[4] for row in rows).most_common(6)}")
    print(f"  ends 16-aligned: {sum(1 for row in rows if row[5] % 16 == 0)}/{len(rows)}")
    print(f"\n{'pack':>12} {'N':>5} {'chains':>7} {'children':>8} {'direct':>6} {'end':>12}")
    for row in rows[:16]:
        print(f"0x{row[0]:010x} {row[1]:>5} {row[2]:>7} {row[3]:>8} {row[4]:>6} 0x{row[5]:010x}")

    if args.tsv:
        args.tsv.parent.mkdir(parents=True, exist_ok=True)
        with args.tsv.open("w") as out:
            out.write("archive\toffset\tcount\tchains\tchildren\tdirect\tend\tok\n")
            for row in rows:
                out.write(f"{args.archive.name}\t0x{row[0]:x}\t{row[1]}\t{row[2]}\t{row[3]}\t"
                          f"{row[4]}\t0x{row[5]:x}\t{row[6]}\n")
        print(f"wrote {args.tsv}")


if __name__ == "__main__":
    main()
