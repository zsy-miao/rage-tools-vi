"""Harvest exact payload sizes from `*_bvh4` descriptors, slice by slice.

Only records that pass the strict bvh4 gate (208 bytes and the full 16-word
tagged-pointer table) yield `+0xa0`, so story/levels structs can never pollute
the size harvest.  For each accepted descriptor the tool records:

    stream offset, allocated size (+0xa0), the u16 pair (+0xa4), both ids

Streams are processed in `--slices` slices and slice `--slice` handles every
n-th stream, so each run finishes inside a shell or harness time limit and the
outputs concatenate.  Slices write `<prefix>.<i>.tsv` and the merge step is a
plain `cat`.
"""

import argparse
import csv
import mmap
import struct
import zlib
from pathlib import Path

BVH4_HEADER = (
    0, 0, 0x50000080, 0, 1, 0, 0x500000A0, 0,
    0x60000000, 0, 0x500000B0, 0, 0x500000C0, 0, 0x50000050, 0,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--out-prefix", type=Path, default=Path("handoff/bvh4-alloc"))
    parser.add_argument("--slice", type=int, default=0)
    parser.add_argument("--slices", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    streams = [(int(row["start"], 16), int(row["end"], 16))
               for row in csv.DictReader(args.index.open(), delimiter="\t")
               if row["kind"] == "zlib" and row["decoded_bytes"] == "208"]
    picked = streams[args.slice::args.slices]
    if args.limit:
        picked = picked[: args.limit]
    out_path = Path(f"{args.out_prefix}.{args.slice}.tsv")
    print(f"{args.archive.name}: {len(streams)} descriptors, slice "
          f"{args.slice}/{args.slices} -> {len(picked)} streams")

    accepted = 0
    with args.archive.open("rb") as handle:
        mm = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        if hasattr(mm, "madvise"):
            try:
                mm.madvise(mmap.MADV_RANDOM)
            except OSError:
                pass
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w") as out:
            out.write("stream\tallocated\tpair_lo\tpair_hi\tid0\tid1\t"
                      "r0x\tr0y\tr0z\tr1x\tr1y\tr1z\tr2x\tr2y\tr2z\n")
            for start, end in picked:
                try:
                    body = zlib.decompress(mm[start:end])
                except zlib.error:
                    continue
                if len(body) != 208:
                    continue
                if struct.unpack_from("<16I", body, 0) != BVH4_HEADER:
                    continue
                allocated, pair = struct.unpack_from("<II", body, 0xA0)
                id0, id1 = struct.unpack_from("<II", body, 0x40)
                # Basis rows are 16-byte padded, so read three floats at
                # 0x50, 0x60 and 0x70 rather than nine contiguous floats.
                rows = (struct.unpack_from("<3f", body, 0x50)
                        + struct.unpack_from("<3f", body, 0x60)
                        + struct.unpack_from("<3f", body, 0x70))
                out.write(f"0x{start:x}\t{allocated}\t{pair & 0xFFFF}\t"
                          f"{pair >> 16}\t0x{id0:08x}\t0x{id1:08x}\t"
                          + "\t".join(f"{value:.6g}" for value in rows) + "\n")
                accepted += 1
        mm.close()
    print(f"accepted {accepted} bvh4 descriptors -> {out_path}")


if __name__ == "__main__":
    main()
