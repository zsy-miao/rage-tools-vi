"""Compare Front B bodies of packs that share N, mode, and format tag.

If the metadata mask is position-deterministic (a stream cipher with a fixed
keystream, or CBC from a fixed chaining value), then equal plaintext bytes at
the same offset stay equal across packs.  Positions that never vary are
therefore constant plaintext fields, and positions that vary are the
payload-dependent fields.  That makes it possible to recover the record stride
without the key.

Reports, for the selected cohort:
  * agreement per byte offset across all sampled bodies
  * runs of constant offsets
  * for each candidate record stride, how well the constant offsets fit a
    fixed residue class (a stride whose constant positions share a residue)
"""

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


def resolve(source, name):
    direct = source / name
    if direct.is_file():
        return direct
    matches = [path for path in source.rglob(name) if path.is_file()]
    if len(matches) != 1:
        raise SystemExit(f"cannot resolve {name} under {source}")
    return matches[0]


def load(path):
    with path.open() as handle:
        rows = []
        for row in csv.DictReader(handle, delimiter="\t"):
            row["offset"] = int(row["offset"], 0)
            for field in ("mode", "version", "count", "front_end", "block",
                          "size_b", "front_a", "trailer"):
                row[field] = int(row[field])
            rows.append(row)
    return rows


def bodies(rows, source):
    handles = {}
    out = []
    for row in rows:
        name = row["archive"]
        if name not in handles:
            handles[name] = resolve(source, name).open("rb")
        handle = handles[name]
        handle.seek(row["offset"] + row["block"])
        data = handle.read(row["size_b"])
        if len(data) == row["size_b"]:
            out.append((row, data))
    for handle in handles.values():
        handle.close()
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, default=Path("handoff/header-census-full.tsv"))
    parser.add_argument("--source", type=Path,
                        default=Path("/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK"))
    parser.add_argument("--archive", default="data.rpf")
    parser.add_argument("--mode", type=lambda s: int(s, 0), default=0x00020007)
    parser.add_argument("--version", type=lambda s: int(s, 0), default=0x00090f02)
    parser.add_argument("--count", type=int, default=None,
                        help="restrict to one N (default: the most frequent N)")
    parser.add_argument("--limit", type=int, default=13)
    parser.add_argument("--min-stable", type=float, default=1.0,
                        help="report offsets stable in at least this fraction of bodies")
    args = parser.parse_args()

    rows = load(args.census)
    rows = [row for row in rows
            if row["archive"] == args.archive
            and row["mode"] == args.mode
            and row["version"] == args.version]
    if not rows:
        raise SystemExit("no headers match the filter")
    counts = Counter(row["count"] for row in rows)
    n = args.count if args.count is not None else counts.most_common(1)[0][0]
    rows = [row for row in rows if row["count"] == n][: args.limit]
    print(f"archive {args.archive}, mode 0x{args.mode:08x}, "
          f"version 0x{args.version:08x}, N={n}, bodies={len(rows)}")

    sampled = bodies(rows, args.source)
    if len(sampled) < 2:
        raise SystemExit("need at least two bodies")
    size = min(len(data) for _, data in sampled)
    print(f"Front B body size: {size} bytes")

    stable = []
    agreement = []
    for offset in range(size):
        values = Counter(data[offset] for _, data in sampled)
        top, hits = values.most_common(1)[0]
        agreement.append(hits / len(sampled))
        if hits / len(sampled) >= args.min_stable:
            stable.append(offset)

    print(f"offsets stable in >= {args.min_stable:.0%} of bodies: "
          f"{len(stable)}/{size} ({len(stable)/size:.1%})")
    runs = []
    for offset in stable:
        if runs and offset == runs[-1][1] + 1:
            runs[-1][1] = offset
        else:
            runs.append([offset, offset])
    print(f"stable runs: {len(runs)}")
    for start, end in runs[:24]:
        print(f"  0x{start:04x}..0x{end:04x} ({end - start + 1} bytes)")

    if len(stable) >= 8:
        print("\ncandidate record strides: constant offsets sharing one residue")
        best = []
        for stride in range(2, 65):
            residues = Counter(offset % stride for offset in stable)
            top, hits = residues.most_common(1)[0]
            best.append((hits / len(stable), stride, top, hits))
        best.sort(reverse=True)
        for share, stride, residue, hits in best[:10]:
            print(f"  stride {stride:>3}: residue {residue:>2} covers "
                  f"{hits}/{len(stable)} ({share:.0%})")

    print("\nagreement histogram (fraction of bodies sharing the majority byte)")
    hist = Counter(round(value, 1) for value in agreement)
    for key in sorted(hist):
        print(f"  {key:.1f}: {hist[key]}")


if __name__ == "__main__":
    main()
