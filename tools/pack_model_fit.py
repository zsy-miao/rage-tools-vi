"""Which simple entry model fits each pack exactly?

`pair_entry_manifest.py` verifies a pack by counting pairs; `entry_model.py`
measures the model per archive. This does it per *pack*, which is the level the
decision actually has to be made at, because mixed packs are mixed internally.

For every pack the tool counts the streams in its window and asks which of these
models reproduces the declared count exactly:

    single    one entry per stream
    pairs     struct stream + data stream
    chains    one entry per chain start (continuation rule)
    structs-1 struct + data, minus one directory stream per pack
    pos-pairs pairs by position, (streams + 1) // 2 — matches 2N and 2N-1

    python3 tools/pack_model_fit.py --out handoff/pack-model-fit.tsv
"""
import argparse
import bisect
import csv
import mmap
import struct
import zlib
from collections import Counter, defaultdict
from pathlib import Path

SELF_TAG = 5
TAG_MAX = 0x0A


def is_struct(body):
    for base in (0, 0x100):
        if base + 0x40 > len(body):
            continue
        hits = 0
        for offset in range(base, base + 0x40, 4):
            value = struct.unpack_from("<I", body, offset)[0]
            tag = value >> 28
            if SELF_TAG <= tag <= TAG_MAX and not value & 0xF:
                hits += 1
        if hits >= 2:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--census", type=Path, default=Path("handoff/header-census-full.tsv"))
    parser.add_argument("--out", type=Path, default=Path("handoff/pack-model-fit.tsv"))
    parser.add_argument("--append", action="store_true")
    args = parser.parse_args()

    packs = sorted((int(r["offset"], 16), int(r["count"]), int(r["front_end"]))
                   for r in csv.DictReader(args.census.open(), delimiter="\t")
                   if r["archive"] == args.archive.name)
    streams = sorted((int(r["start"], 16), int(r["end"], 16),
                      int(r["decoded_bytes"] or 0))
                     for r in csv.DictReader(args.index.open(), delimiter="\t")
                     if r["kind"] == "zlib")
    starts = [s[0] for s in streams]

    kinds = []
    with args.archive.open("rb") as handle:
        mm = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        STRUCT_LIMIT = 1 << 16      # a struct stream is a descriptor, not payload
        for offset, end, decoded in streams:
            # Decompressing every stream just to classify it dominated the runtime
            # (1.1 M streams in levels). Anything larger than 64 KiB cannot be a
            # struct stream, so the decode is skipped for it.
            if decoded > STRUCT_LIMIT:
                kinds.append(False)
                continue
            try:
                kinds.append(is_struct(zlib.decompress(mm[offset:end])))
            except zlib.error:
                kinds.append(False)
        mm.close()

    def chains(indices):
        count = 0
        previous = None
        for index in indices:
            stream = streams[index]
            continues = (previous is not None and previous[0] == 65536
                         and stream[0] == ((previous[1] + 15) // 16 * 16))
            if not continues:
                count += 1
            previous = (stream[2], stream[1])
        return count

    rows = []
    for position, (offset, declared, front_end) in enumerate(packs):
        limit = (packs[position + 1][0] if position + 1 < len(packs)
                 else streams[-1][1] if streams else 0)
        low = bisect.bisect_left(starts, offset + front_end)
        high = bisect.bisect_left(starts, limit)
        window = list(range(low, high))
        if not window or declared <= 0:
            continue
        structs = sum(1 for index in window if kinds[index])
        models = {
            "single": len(window),
            "pairs": structs,
            "chains": chains(window),
            "data_streams": len(window) - structs,
            # Packs can carry one struct stream that is the pack's own directory
            # row rather than an entry, which makes the struct count N + 1.
            "structs-1": structs - 1,
            # Pairs counted by position, not by classification. Fits both 2N
            # streams and the 2N-1 case where one entry has only its data half.
            "pos-pairs": (len(window) + 1) // 2,
        }
        exact = [name for name, value in models.items() if value == declared]
        rows.append((args.archive.name, f"0x{offset:x}", declared, len(window),
                     structs, models["chains"], ",".join(exact) or "-"))

    # A first append to a missing file still needs the header.
    fresh = not args.out.exists() or args.out.stat().st_size == 0
    mode = "a" if args.append else "w"
    with args.out.open(mode) as out:
        if mode == "w" or fresh:
            out.write("archive\tpack\tdeclared\tstreams\tstructs\tchains\texact_models\n")
        for row in rows:
            out.write("\t".join(str(c) for c in row) + "\n")
    matched = sum(1 for row in rows if row[6] != "-")
    print(f"{args.archive.name}: {matched} of {len(rows)} packs fit a simple model exactly")
    print("  winners:", Counter(row[6] for row in rows if row[6] != "-").most_common(5))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
