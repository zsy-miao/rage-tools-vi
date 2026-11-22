"""Census every RPF9 header in a set of archives and fit Front B size laws.

Scans for the `9FPR` magic at 16-byte alignment (nested packs need not start on
a 0x1000 boundary), validates the three observed metadata regions, and reports
the distribution of the mode and version words. For each (mode, version) group
it tests candidate Front B laws of the form align16(a*N + c) and keeps the ones
that hold for every header in the group.

Outputs a tab-separated table to stdout and, with --tsv, to a file.
"""

import argparse
import mmap
import struct
from collections import Counter, defaultdict
from pathlib import Path

MAGIC = b"9FPR"
HEADER_SIZE = 0x60
ALIGN = 16

# Candidate record strides and additive header terms for Front B.
STRIDES = (8, 10, 12, 14, 16, 20, 24)
HEADERS = (0, 4, 8, 12, 16, 24, 32)


def align16(value):
    return (value + ALIGN - 1) // ALIGN * ALIGN


def scan_header(mv, offset):
    """Return a validated header dict for the magic at `offset`, or None."""
    if offset + HEADER_SIZE > len(mv):
        return None
    header = mv[offset : offset + HEADER_SIZE]
    if header[:4] != MAGIC:
        return None
    front_end, block, trailer = struct.unpack_from("<III", header, 4)
    if front_end % ALIGN or block % ALIGN or trailer % ALIGN:
        return None
    if not (HEADER_SIZE <= block <= front_end):
        return None
    if front_end + trailer > len(mv) - offset:
        return None
    mode = struct.unpack_from("<I", header, 0x20)[0]
    count = struct.unpack_from("<I", header, 0x24)[0]
    version = struct.unpack_from("<I", header, 0x2C)[0]
    if count == 0 or count > 1_000_000:
        return None
    return {
        "offset": offset,
        "front_end": front_end,
        "block": block,
        "trailer": trailer,
        "mode": mode,
        "count": count,
        "version": version,
        "size_b": front_end - block,
        "front_a": block - HEADER_SIZE,
        "tail32": bytes(header[0x40:0x60]).hex(),
    }


def census(path):
    rows = []
    with path.open("rb") as handle:
        size = path.stat().st_size
        if size < HEADER_SIZE:
            return rows
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mv:
            pos = mv.find(MAGIC)
            while pos != -1:
                if pos % ALIGN == 0:
                    row = scan_header(mv, pos)
                    if row:
                        row["archive"] = path.name
                        rows.append(row)
                pos = mv.find(MAGIC, pos + 1)
    return rows


def fit_laws(rows):
    """Return every (stride, header) law that holds for all rows."""
    laws = []
    for stride in STRIDES:
        for head in HEADERS:
            if all(row["size_b"] == align16(stride * row["count"] + head) for row in rows):
                laws.append((stride, head))
    return laws


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument("--tsv", type=Path)
    args = parser.parse_args()

    fields = [
        "archive",
        "offset",
        "mode",
        "version",
        "count",
        "front_end",
        "block",
        "size_b",
        "front_a",
        "trailer",
    ]
    out = None
    if args.tsv:
        args.tsv.parent.mkdir(parents=True, exist_ok=True)
        out = args.tsv.open("w")
        out.write("\t".join(fields) + "\n")
        out.flush()

    rows = []
    for path in args.archives:
        found = census(path)
        print(f"{path.name}: {len(found)} headers", flush=True)
        rows.extend(found)
        if out:
            for row in found:
                out.write(
                    "\t".join(
                        f"0x{row['offset']:x}" if field == "offset" else str(row[field])
                        for field in fields
                    )
                    + "\n"
                )
            out.flush()
    if out:
        out.close()
        print(f"wrote {args.tsv} ({len(rows)} rows)")

    print(f"\ntotal headers: {len(rows)}")

    tails = Counter(row["tail32"] for row in rows)
    print(f"distinct +0x40..0x60 blocks: {len(tails)}")
    for tail, n in tails.most_common(4):
        print(f"  {n:4d}  {tail}")

    groups = defaultdict(list)
    for row in rows:
        groups[(row["mode"], row["version"])].append(row)

    print("\nmode/version groups and Front B laws (align16(a*N + c))")
    print("mode\tversion\theaders\tN values\tN mod 4\tB values\tlaws")
    for (mode, version), group in sorted(groups.items(), key=lambda item: -len(item[1])):
        counts = sorted({row["count"] for row in group})
        nmod = dict(Counter(row["count"] % 4 for row in group))
        sizes = sorted({row["size_b"] for row in group})
        laws = fit_laws(group)
        law_text = ", ".join(f"{a}N+{c}" for a, c in laws) or "none"
        count_text = ",".join(str(c) for c in counts[:6]) + ("…" if len(counts) > 6 else "")
        size_text = ",".join(str(s) for s in sizes[:5]) + ("…" if len(sizes) > 5 else "")
        print(
            f"0x{mode:08x}\t0x{version:08x}\t{len(group)}\t{count_text}\t{nmod}\t"
            f"{size_text}\t{law_text}"
        )



if __name__ == "__main__":
    main()
