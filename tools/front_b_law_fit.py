"""Fit Front A, Front B, and trailer sizes against N from a header census TSV.

Reads the table written by `tools/header_census.py` and, for each
(mode, version) group, tests additive laws of the form align16(a*N + c) for
every region.  When no law holds it reports the residual distribution against
the two reference laws (10N for Front B, 12N+12 for the trailer suffixes) so
the deviation can be characterized instead of guessed.
"""

import argparse
import struct
from collections import Counter, defaultdict
from pathlib import Path

ALIGN = 16


def align16(value):
    return (value + ALIGN - 1) // ALIGN * ALIGN


def load(path):
    rows = []
    with path.open() as handle:
        header = handle.readline().rstrip("\n").split("\t")
        for line in handle:
            values = line.rstrip("\n").split("\t")
            row = dict(zip(header, values))
            for field in ("offset", "front_end", "block"):
                row[field] = int(row[field], 0)
            for field in ("mode", "version", "count", "size_b", "front_a", "trailer"):
                row[field] = int(row[field])
            rows.append(row)
    return rows


def fit(group, field, max_stride=400):
    """Return (stride, addend_lo, addend_hi) laws that hold for every row.

    For a fixed stride `a`, the rows constrain the additive term to
    [max(B - aN) - 15, min(B - aN)] because Front B is 16-byte aligned.  The
    interval is non-empty exactly when the residual spread is at most 15.
    """
    laws = []
    for stride in range(1, max_stride + 1):
        residuals = [row[field] - stride * row["count"] for row in group]
        low, high = min(residuals), max(residuals)
        if high - low <= ALIGN - 1:
            lo, hi = max(low, 0), high
            if lo <= hi:
                laws.append((stride, lo, hi))
    return laws


def compact(laws):
    return ", ".join(
        f"{a}N+{c}" if lo == hi else f"{a}N+[{lo}..{hi}]" for a, lo, hi in laws
    ) or "none"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, default=Path("handoff/header-census-full.tsv"))
    parser.add_argument("--field", default="size_b", choices=("size_b", "front_a", "trailer"))
    parser.add_argument("--mode", type=lambda s: int(s, 0), default=None,
                        help="only this mode word")
    parser.add_argument("--show-rows", type=int, default=0,
                        help="print this many (N, value) rows per group")
    args = parser.parse_args()

    rows = load(args.census)
    if args.mode is not None:
        rows = [row for row in rows if row["mode"] == args.mode]
    print(f"rows: {len(rows)}")

    groups = defaultdict(list)
    for row in rows:
        groups[(row["mode"], row["version"])].append(row)

    for (mode, version), group in sorted(groups.items(), key=lambda item: -len(item[1])):
        pairs = sorted({(row["count"], row[args.field]) for row in group})
        repeated = {n: len({v for m, v in pairs if m == n}) for n, _ in pairs}
        ambiguous = {n: k for n, k in repeated.items() if k > 1}
        print(
            f"\nmode 0x{mode:08x} / 0x{version:08x}: {len(group)} headers, "
            f"{len(pairs)} distinct (N, {args.field}) pairs"
        )
        print(f"  N range {pairs[0][0]}..{pairs[-1][0]}, {args.field} range "
              f"{min(v for _, v in pairs)}..{max(v for _, v in pairs)}")
        if ambiguous:
            examples = ", ".join(f"N={n}:{k}" for n, k in list(ambiguous.items())[:6])
            print(f"  same N with different {args.field}: {examples}")
        print(f"  laws: {compact(fit(group, args.field))}")
        if args.show_rows:
            for n, value in pairs[: args.show_rows]:
                print(f"    N={n:<6} {args.field}={value:<8} "
                      f"a10={align16(10 * n):<8} d10={value - align16(10 * n):<6} "
                      f"a12={align16(12 * n):<8} d12={value - align16(12 * n):<6} "
                      f"a12p={align16(12 * n + 12):<8} d12p={value - align16(12 * n + 12)}")


if __name__ == "__main__":
    main()
