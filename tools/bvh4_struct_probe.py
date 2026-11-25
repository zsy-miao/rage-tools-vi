"""Tabulate the small serialized structs inside `core_bvh4` entries.

Descriptor-less entries decode to records of 160, 192, 240, 256, 272, 544, 800
and other sizes.  Each begins with the same eight-slot header as the 208-byte
descriptor, but the `0x5`-tagged self-relative pointers sit at different offsets,
which suggests a fixed struct layout per size.

For each size this tool decodes a few samples and reports:

  * whether the first 0x40 bytes are constant within the size class,
  * the tagged-pointer offsets and whether they stay inside the record,
  * the full byte dump of one representative.
"""

import argparse
import bisect
import csv
import mmap
import struct
import zlib
from collections import Counter, defaultdict
from pathlib import Path


def load_windows(census, archive):
    heads = sorted((int(row["offset"], 16), int(row["count"]))
                   for row in csv.DictReader(census.open(), delimiter="\t")
                   if row["archive"] == archive)
    return heads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path,
                        default=Path("/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK/pack/core_bvh4/core_bvh4.rpf"))
    parser.add_argument("--index", type=Path, default=Path("output/index/core_bvh4.tsv"))
    parser.add_argument("--census", type=Path, default=Path("handoff/header-census-full.tsv"))
    parser.add_argument("--samples", type=int, default=4)
    args = parser.parse_args()

    heads = load_windows(args.census, args.archive.name)
    streams = sorted((int(row["start"], 16), int(row["end"], 16), int(row["decoded_bytes"] or 0))
                     for row in csv.DictReader(args.index.open(), delimiter="\t")
                     if row["kind"] == "zlib")
    starts = [row[0] for row in streams]

    unpaired = []
    for index, (head, count) in enumerate(heads):
        end = heads[index + 1][0] if index + 1 < len(heads) else 1 << 62
        low = bisect.bisect_left(starts, head)
        high = bisect.bisect_left(starts, end)
        window = streams[low:high]
        paired = set()
        at = 0
        descriptors = 0
        while at < len(window):
            if window[at][2] == 208 and at + 1 < len(window):
                paired.update({at, at + 1})
                descriptors += 1
                at += 2
            else:
                at += 1
        if count - descriptors <= 0:
            continue
        unpaired.extend(row for pos, row in enumerate(window)
                        if pos not in paired and row[2] != 65536)

    sizes = Counter(row[2] for row in unpaired)
    print(f"unpaired small records: {len(unpaired)}, distinct sizes: {len(sizes)}")
    print("top sizes:", sizes.most_common(8))

    by_size = defaultdict(list)
    for stream in unpaired:
        by_size[stream[2]].append(stream)

    with args.archive.open("rb") as handle:
        mm = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        for size, group in sorted(by_size.items(), key=lambda item: -len(item[1]))[:6]:
            if size > 4096:
                continue
            bodies = []
            for stream in group[: args.samples]:
                try:
                    bodies.append(zlib.decompress(mm[stream[0]:stream[1]])[:size])
                except zlib.error:
                    continue
            if not bodies:
                continue
            heads_set = {body[:0x40] for body in bodies}
            slots = [struct.unpack_from("<8I", body, 0) for body in bodies[:1]][0]
            tag5 = [value & 0x0FFFFFFF for value in slots if (value >> 28) == 5]
            print(f"\nsize {size}: {len(group)} records, header unique: {len(heads_set)} "
                  f"(of {len(bodies)})")
            print(f"  slots: {' '.join(f'0x{v:08x}' for v in slots)}")
            print(f"  tag-5 offsets: {[hex(v) for v in tag5]} "
                  f"inside: {all(v < size for v in tag5)}")
            if len(heads_set) == 1 and len(group) > 1:
                print("  header is constant within the size class")
            body = bodies[0]
            for at in range(0, min(size, 0x100), 16):
                print(f"    +0x{at:03x} {body[at:at + 16].hex(' ')}")
        mm.close()


if __name__ == "__main__":
    main()
