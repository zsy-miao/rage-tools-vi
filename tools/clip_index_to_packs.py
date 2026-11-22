"""Split index ranges that cross a pack boundary, one row per pack.

Packs are independent archives: the loader builds one archive object per pack, so a
span of bytes cannot belong to two of them. The partitioner does not know this — it
works on stored-byte runs and only learns where a pack ends from the next `9FPR`
magic — which is why 32 `unclassified` spans currently cross a boundary while every
classified payload stays inside its own pack.

This rewrites an index so that a crossing range becomes two rows, one per pack, with
the same `kind` and the stored size recomputed. Ranges are written exactly as read,
so the tiling invariant still holds: the pieces cover the same bytes as the original.

    python3 tools/clip_index_to_packs.py --all --dry-run
    python3 tools/clip_index_to_packs.py --all
"""

import argparse
import csv
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def pack_starts(path):
    out = []
    size = path.stat().st_size
    with path.open("rb") as handle:
        for offset in range(0, max(0, size - 0x60), 0x4000):
            handle.seek(offset)
            header = handle.read(0x60)
            if len(header) < 0x60 or header[:4] != b"9FPR":
                continue
            front_end, block, trailer = struct.unpack_from("<III", header, 4)
            if not (0x60 < block <= front_end <= size - offset):
                continue
            out.append(offset)
    return out


def clip(archive, index, write):
    starts = pack_starts(archive)
    if len(starts) < 2:
        return 0, 0
    bounds = starts[1:]
    rows = list(csv.DictReader(index.open(), delimiter="\t"))
    if not rows:
        return 0, 0
    fields = list(rows[0])
    split = 0
    out_rows = []
    for row in rows:
        start, stop = int(row["start"], 16), int(row["end"], 16)
        cuts = [bound for bound in bounds if start < bound < stop]
        if not cuts:
            out_rows.append(row)
            continue
        split += 1
        position = start
        for cut in cuts + [stop]:
            piece = dict(row)
            piece["start"] = f"0x{position:x}"
            piece["end"] = f"0x{cut:x}"
            if "stored_bytes" in piece:
                piece["stored_bytes"] = str(cut - position)
            out_rows.append(piece)
            position = cut
    if write:
        with index.open("w") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t",
                                    lineterminator="\n")
            writer.writeheader()
            writer.writerows(out_rows)
    return split, len(out_rows) - len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archives", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--index-dir", type=Path, default=ROOT / "output/index")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    targets = list(args.archives)
    if args.all:
        targets = sorted(Path(".").glob("*.rpf"))
    if not targets:
        sys.exit("give an archive or --all")

    total = 0
    for archive in targets:
        index = args.index_dir / (archive.stem + ".tsv")
        if not index.is_file():
            print(f"{archive.name}: no index")
            continue
        split, added = clip(archive, index, not args.dry_run)
        if split:
            print(f"{archive.name}: {split} crossing range(s) -> {added:+d} rows"
                  + (" (dry run)" if args.dry_run else ""))
        total += split
    print(f"crossing ranges handled: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
