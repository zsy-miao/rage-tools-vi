"""Probe every archive's largest `unclassified` span for internal structure.

Two archives were examined by hand and both turned out to carry structure the
partitioner could not name: `movies.rpf` is Bink2 containers, `core_restofworld.rpf`
has a sorted 24-bit offset table. This runs the same first look over every archive:

* how much of the archive is `unclassified`;
* the largest span's length, its leading zero run, and its byte entropy;
* whether a 4-byte-stride table is present — measured as the fraction of steps in
  which the first three bytes (little-endian) increase, which is what a sorted offset
  table looks like and what raw payload does not.

    python3 tools/unclassified_probe.py --source $RAGE_SRC
"""

import argparse
import os
import csv
import math
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "output" / "index"
WINDOW = 4096


def entropy(data):
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum(v / n * math.log2(v / n) for v in counts.values())


def find_archive(name, sources):
    for directory in sources:
        candidate = directory / f"{name}.rpf"
        if candidate.is_file():
            return candidate
    # archives are nested under pack/<name>/<name>.rpf in the download tree
    for directory in sources:
        for candidate in directory.glob(f"**/{name}.rpf"):
            return candidate
    return None


def monotonic_u24(window):
    values = [int.from_bytes(window[i:i + 3], "little")
              for i in range(0, len(window) - 3, 4)]
    if len(values) < 8:
        return 0.0
    steps = sum(1 for a, b in zip(values, values[1:]) if b > a)
    return steps / (len(values) - 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", nargs="*", type=Path,
                        default=[Path("$RAGE_SRC"),
                                 Path("/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK")])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    rows = []
    for index in sorted(INDEX.glob("*.tsv")):
        name = index.stem
        if "-" in name:
            continue
        archive = find_archive(name, args.source)
        if archive is None:
            continue
        spans = []
        total = 0
        unclassified = 0
        with index.open() as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                start, stop = int(row["start"], 16), int(row["end"], 16)
                total = max(total, stop)
                if row["kind"] == "unclassified":
                    unclassified += stop - start
                    spans.append((start, stop))
        if not spans:
            continue
        spans.sort(key=lambda s: s[1] - s[0], reverse=True)
        start, stop = spans[0]
        with archive.open("rb") as handle:
            handle.seek(start)
            head = handle.read(WINDOW)
            handle.seek(start + max(0, (stop - start) // 2))
            middle = handle.read(WINDOW)
        first_nonzero = next((i for i, b in enumerate(head) if b), -1)
        rows.append({
            "archive": name,
            "size": total,
            "unclassified": unclassified,
            "share": unclassified / total if total else 0,
            "largest": stop - start,
            "first_nonzero": first_nonzero,
            "head_entropy": entropy(head),
            "mid_entropy": entropy(middle),
            # measure at the first non-zero byte: a span often opens with zeros or a
            # short header, and a table test applied to those reports noise.
            "u24_monotonic": (monotonic_u24(head[first_nonzero:])
                              if 0 <= first_nonzero < len(head) - 32 else 0.0),
        })

    if not rows:
        sys.exit("no archives found next to their indexes")
    header = (f"{'archive':24s} {'size':>13s} {'unclass':>8s} {'largest':>13s} "
              f"{'1st!0':>7s} {'H head':>7s} {'H mid':>6s} {'u24@1st':>8s}")
    print(header)
    print("-" * len(header))
    for row in rows:
        print(f"{row['archive']:24s} {row['size']:13,d} {row['share']:8.1%} "
              f"{row['largest']:13,d} {row['first_nonzero']:7d} "
              f"{row['head_entropy']:7.2f} {row['mid_entropy']:6.2f} "
              f"{row['u24_monotonic']:8.1%}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as handle:
            handle.write("archive\tsize\tunclassified\tshare\tlargest\tfirst_nonzero\t"
                         "head_entropy\tmid_entropy\tu24_monotonic\n")
            for row in rows:
                handle.write(f"{row['archive']}\t{row['size']}\t{row['unclassified']}\t"
                             f"{row['share']:.4f}\t{row['largest']}\t"
                             f"{row['first_nonzero']}\t{row['head_entropy']:.2f}\t"
                             f"{row['mid_entropy']:.2f}\t{row['u24_monotonic']:.4f}\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
