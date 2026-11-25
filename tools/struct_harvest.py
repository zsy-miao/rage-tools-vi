"""Unified struct harvest across archives, with the two guards.

Guard 1 — `+0xa0` is only a class field of the 208-byte BVH descriptor.  The
scanner extracts it only when the struct matches the bvh4 layout exactly: 208
bytes and the `0x50000080/0xa0/0xb0/0xc0/0x50` pointer table with `1` at
`+0x10` and `0x60000000` at `+0x20`.  Everything else is left alone, so story
and levels structs cannot pollute the size harvest.

Guard 2 — segment nibbles.  A candidate pointer is a `u32` whose upper nibble is
`5..0xA` and whose low four bits are zero (every observed self-relative pointer
is 16-byte aligned).  Nibble `5` addresses sub-structures inside the same stream;
nibbles `6` and above are external segments.  Per root struct the scanner
records how many external pointers it sees and the highest nibble, so a stream's
attachment count comes from the serializer instead of from a size heuristic.

Also reports the index-only entry ratios so the attachment counts can be checked
against declared N without reading the whole archive.
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
EXTERNAL_TAG_MIN = 6
TAG_MAX = 0x0A


def load_windows(census, archive):
    return sorted((int(row["offset"], 16), int(row["count"]))
                  for row in csv.DictReader(census.open(), delimiter="\t")
                  if row["archive"] == archive)


def load_streams(index):
    return sorted((int(row["start"], 16), int(row["end"], 16), int(row["decoded_bytes"] or 0))
                  for row in csv.DictReader(index.open(), delimiter="\t")
                  if row["kind"] == "zlib")


BVH4_HEADER = (
    0, 0, 0x50000080, 0, 1, 0, 0x500000A0, 0,
    0x60000000, 0, 0x500000B0, 0, 0x500000C0, 0, 0x50000050, 0,
)


def is_bvh4_descriptor(body):
    """Exact bvh4 gate: 208 bytes and the full 16-word pointer table."""
    if len(body) != 208:
        return False
    return struct.unpack_from("<16I", body, 0) == BVH4_HEADER


def scan_struct(body, base=0, strict=True):
    """Return (pointers, external, max_tag, self_count) for one struct header."""
    # Only the struct header carries the pointer table; scanning the whole
    # payload would count random words as pointers (a 6 MB body produced dozens
    # of false "external" hits per sample).
    pointers = []
    for offset in range(base, min(base + 0x40, len(body) - 3), 4):
        value = struct.unpack_from("<I", body, offset)[0]
        tag = value >> 28
        if not (SELF_TAG <= tag <= TAG_MAX):
            continue
        if value & 0xF:
            continue
        target = value & 0x0FFFFFFF
        if strict and tag == SELF_TAG and not (base <= target < len(body)):
            continue
        pointers.append((offset, tag, target))
    # A self-tagged pointer whose target lies past the struct body addresses the
    # entry's attached segment, not this stream; count it apart from in-body
    # self pointers so the attachment budget can be accounted for.
    self_count = sum(1 for _, tag, target in pointers
                     if tag == SELF_TAG and base <= target < len(body))
    beyond = sum(1 for _, tag, target in pointers
                 if tag == SELF_TAG and target >= len(body))
    external = [pointer for pointer in pointers if pointer[1] >= EXTERNAL_TAG_MIN]
    max_tag = max((pointer[1] for pointer in pointers), default=0)
    return pointers, external, max_tag, self_count, beyond


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", nargs="+", required=True,
                        help="name:index pairs, e.g. story000.rpf:output/index/story000.tsv")
    parser.add_argument("--source", type=Path,
                        default=Path("/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK"))
    parser.add_argument("--census", type=Path, default=Path("handoff/header-census-full.tsv"))
    parser.add_argument("--sample", type=int, default=300)
    parser.add_argument("--relaxed", action="store_true",
                        help="accept tag-5 pointers whose target leaves the stream")
    parser.add_argument("--tsv", type=Path, default=Path("handoff/struct-harvest.tsv"))
    parser.add_argument("--summary", type=Path, default=Path("handoff/struct-summary.tsv"))
    args = parser.parse_args()

    def resolve(name):
        direct = args.source / name
        if direct.is_file():
            return direct
        matches = [path for path in args.source.rglob(name) if path.is_file()]
        if len(matches) != 1:
            raise SystemExit(f"cannot resolve {name}")
        return matches[0]

    rows = []
    summary = []
    for spec in args.archives:
        name, index = spec.split(":", 1)
        index = Path(index)
        archive = resolve(name)
        windows = load_windows(args.census, name)
        streams = load_streams(index)
        starts = [stream[0] for stream in streams]

        # Index-only context: streams and chains per declared entry.
        declared = sum(count for _, count in windows)
        nested = len(windows) - 1
        entries = declared - nested
        print(f"\n=== {name}: packs {len(windows)}, streams {len(streams)}, "
              f"declared entries {entries}, streams/entry {len(streams)/max(1, entries):.2f}")

        # Strided sampling is biased when struct streams cluster in long runs
        # (navmeshes has 2,447 structs in a row), so sample randomly.
        import random
        rng = random.Random(0xB0DE)
        picked = rng.sample(streams, min(args.sample, len(streams)))
        picked.sort()
        shapes = Counter()
        nibbles = Counter()
        external_counts = Counter()
        bvh4 = 0
        bases = Counter()
        beyond_counts = Counter()
        histogram = Counter()
        with archive.open("rb") as handle:
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
                # The struct header is at offset 0 in the bvh4 split, and after
                # the 256-byte payload header elsewhere.
                best = None
                for base in (0, 0x100):
                    if base + 0x40 <= len(body):
                        candidate = scan_struct(body, base, strict=not args.relaxed)
                        if best is None or len(candidate[0]) > len(best[0]):
                            best = candidate
                            best_base = base
                if best is None:
                    continue
                pointers, external, max_tag, self_count, beyond = best
                size = len(body)
                is_struct = len(pointers) >= 2
                shapes["struct" if is_struct else "no_struct"] += 1
                histogram[min(size // 256, 32)] += 1
                bases[best_base] += 1
                if is_struct:
                    nibbles[max_tag] += 1
                    external_counts[len(external)] += 1
                    beyond_counts[beyond] += 1
                if is_bvh4_descriptor(body):
                    best_base = 0
                    bvh4 += 1
                    allocated, pair = struct.unpack_from("<II", body, 0xA0)
                    rows.append({
                        "archive": name,
                        "stream": f"0x{stream[0]:x}",
                        "kind": "bvh4",
                        "decoded": size,
                        "self_pointers": self_count,
                        "external": len(external),
                        "max_tag": max_tag,
                        "allocated": allocated,
                        "pair_lo": pair & 0xFFFF,
                        "pair_hi": pair >> 16,
                    })
                elif is_struct:
                    rows.append({
                        "archive": name,
                        "stream": f"0x{stream[0]:x}",
                        "kind": "struct",
                        "decoded": size,
                        "self_pointers": self_count,
                        "external": len(external),
                        "max_tag": max_tag,
                        "allocated": "",
                        "pair_lo": "",
                        "pair_hi": "",
                    })
            mm.close()

        total = sum(shapes.values())
        summary.append({
            "archive": name,
            "packs": len(windows),
            "streams": len(streams),
            "entries": entries,
            "streams_per_entry": round(len(streams) / max(1, entries), 3),
            "sampled": total,
            "struct_share": round(shapes["struct"] / max(1, total), 4),
            "bvh4_descriptors": bvh4,
            "max_tag_top": max(nibbles, key=nibbles.get) if nibbles else "",
            "tag5_share": round(nibbles.get(5, 0) / max(1, shapes["struct"]), 4),
            "mean_external": round(
                sum(k * v for k, v in external_counts.items()) / max(1, sum(external_counts.values())), 3)
            if external_counts else "",
            "implied_attachments": round(len(streams) / max(1, entries) - 1, 3),
        })
        print(f"  sampled {total}: structs {shapes['struct']} "
              f"({shapes['struct'] / max(1, total):.1%}), bvh4 descriptors {bvh4}")
        print(f"  struct header offset: {dict(sorted(bases.items()))}")
        print(f"  max segment nibble per struct: {dict(sorted(nibbles.items()))}")
        print(f"  external pointers per struct: {dict(sorted(external_counts.items())[:8])}")
        print(f"  tag-5 pointers past the body: {dict(sorted(beyond_counts.items())[:8])}")
        if external_counts:
            mean = sum(k * v for k, v in external_counts.items()) / sum(external_counts.values())
            attached = sum(k * v for k, v in beyond_counts.items()) / max(1, sum(beyond_counts.values()))
            print(f"  mean external pointers per struct: {mean:.2f}, "
                  f"mean past-body self pointers: {attached:.2f}, "
                  f"sum: {mean + attached:.2f} "
                  f"(index ratio implies {len(streams)/max(1, entries) - 1:.2f} attachments/entry)")

    args.summary.parent.mkdir(parents=True, exist_ok=True)
    summary_fields = ["archive", "packs", "streams", "entries", "streams_per_entry",
                      "sampled", "struct_share", "bvh4_descriptors", "max_tag_top",
                      "tag5_share", "mean_external", "implied_attachments"]
    with args.summary.open("w") as out:
        out.write("\t".join(summary_fields) + "\n")
        for row in summary:
            out.write("\t".join(str(row[field]) for field in summary_fields) + "\n")
    print(f"wrote {args.summary} ({len(summary)} archives)")

    fields = ["archive", "stream", "kind", "decoded", "self_pointers", "external",
              "max_tag", "allocated", "pair_lo", "pair_hi"]
    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w") as out:
        out.write("\t".join(fields) + "\n")
        for row in rows:
            out.write("\t".join(str(row[field]) for field in fields) + "\n")
    print(f"\nwrote {args.tsv} ({len(rows)} struct rows)")


if __name__ == "__main__":
    main()
