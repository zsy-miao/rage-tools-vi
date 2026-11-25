"""Check the three-boundary pack model against the index of every archive.

The model, all from the header plus the next magic:

    header       [pack,         pack + 0x40)
    front region [pack,         pack + word_04)
    payload      [pack + word_04, pack_end - word_0c)
    trailer      [pack_end - word_0c, pack_end)

where `pack_end` is the next `9FPR` header, or the file size for the last pack.

If the model is right, the index ranges sit inside the payload window and cover it
almost entirely — the remainder being inter-range alignment. A pack whose coverage
is low, or whose ranges escape the window, is evidence against the model.

    python3 tools/pack_extent_check.py data.rpf
    python3 tools/pack_extent_check.py --all
"""

import argparse
import csv
import struct
from collections import defaultdict
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def headers(path):
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
            out.append((offset, front_end, trailer))
    return out, size


def ranges(index):
    if not index.is_file():
        return None
    with index.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            yield int(row["start"], 16), int(row["end"], 16), row.get("kind", "")


def union_length(intervals):
    """Length of the union of half-open intervals."""
    total = 0
    current_start = current_end = None
    for start, stop in sorted(intervals):
        if start >= stop:
            continue
        if current_start is None:
            current_start, current_end = start, stop
        elif start <= current_end:
            current_end = max(current_end, stop)
        else:
            total += current_end - current_start
            current_start, current_end = start, stop
    if current_start is not None:
        total += current_end - current_start
    return total


def check(archive, index, verbose):
    found, size = headers(archive)
    if not found:
        print(f"{archive.name}: no headers")
        return 0, 0, 0, {}
    spans = list(ranges(index))
    if spans is None:
        print(f"{archive.name}: no index at {index}")
        return 0, 0, 0, {}

    covered_total = window_total = 0
    escape = 0
    crossings = defaultdict(int)
    worst = (1.0, None)
    for position, (offset, front_end, trailer) in enumerate(found):
        end = found[position + 1][0] if position + 1 < len(found) else size
        window_start = offset + front_end
        window_end = max(window_start, end - trailer)
        window = max(0, window_end - window_start)
        pieces = []
        for start, stop, kind in spans:
            if stop <= window_start or start >= window_end:
                continue
            if start < offset or stop > end:
                escape += 1
                crossings[kind] += 1
            pieces.append((max(start, window_start), min(stop, window_end)))
        # union, not a sum: overlapping ranges would otherwise hide a gap
        covered = union_length(pieces)
        covered_total += covered
        window_total += window
        if window:
            share = covered / window
            if share < worst[0]:
                worst = (share, (offset, window, covered))
        if verbose:
            print(f"  pack +0x{offset:x}  front 0x{front_end:x}  trailer {trailer}  "
                  f"payload {window}  covered {covered}  {covered / window:.4%}" if window
                  else f"  pack +0x{offset:x}  empty window")
    share = covered_total / window_total if window_total else 0
    print(f"{archive.name}: {len(found)} packs, payload {window_total:,} B, "
          f"covered {covered_total:,} B ({share:.2%}), escaped ranges {escape}")
    if crossings:
        detail = ", ".join(f"{kind or '?'}={count}" for kind, count in
                           sorted(crossings.items(), key=lambda item: -item[1]))
        print(f"  ranges crossing a pack boundary: {detail}")
    if worst[1]:
        offset, window, covered = worst[1]
        print(f"  weakest pack +0x{offset:x}: {covered}/{window} = {covered / window:.2%}")
    return len(found), share, escape, crossings


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archives", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true", help="every *.rpf with an index")
    parser.add_argument("--index-dir", type=Path, default=ROOT / "output/index")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    targets = list(args.archives)
    if args.all:
        for path in sorted(Path(".").glob("*.rpf")):
            targets.append(path)
    if not targets:
        sys.exit("give an archive or --all")

    failures = 0
    for archive in targets:
        index = args.index_dir / (archive.stem + ".tsv")
        packs, share, escape, crossings = check(archive, index, args.verbose)
        # spans that our partitioner could not classify may run across a pack
        # boundary; every classified range must stay inside its own pack.
        hard = sum(count for kind, count in crossings.items() if kind != "unclassified")
        if hard or share < 0.99:
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
