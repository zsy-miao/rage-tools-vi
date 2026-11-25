"""Extract and census the AWC containers the old pass missed.

`audio.rpf` was extracted once, from a `0xff21` scan, producing 6,625 containers. The
index built by `tools/adat_index.py` finds **7,159** — the extra 534 sit in the gaps
between the ones that pass covered, and have never been written out.

This extracts those gaps and reads each container's chunk table directly, so the
result is a count of streams, codecs and payload bytes rather than a claim about them.

    python3 tools/extract_adat_gaps.py --archive /src/audio.rpf \\
        --all output/index/audio-adat.tsv --known output/extracted/audio-awc/manifest.tsv \\
        --out-dir /out/audio-gap --census handoff/audio-gap-census.tsv
"""

import argparse
import csv
import struct
import sys
from collections import Counter
from pathlib import Path

ALIGN = 0x800
KNOWN_TYPES = {0x55, 0x36, 0x76, 0xA3, 0xFA, 0x48, 0x5C, 0x68, 0x2B, 0x5A, 0xD9, 0xBD}
TABLE_AT = {0xFF21: lambda count: 0x50, 0xFF02: lambda count: 0x10 + 4 * count}


def header(blob):
    if len(blob) < 16 or blob[:4] != b"ADAT":
        return None
    version, flags, count, header_size = struct.unpack_from("<HHII", blob, 4)
    return version, flags, count, header_size


def chunk_table(blob, flags, count, header_size):
    """(start, records) for the chunk table, by the variant rules."""
    if flags in TABLE_AT:
        start = TABLE_AT[flags](count)
        span = header_size - start
        if span > 0 and span % (8 * count) == 0 and 1 <= span // (8 * count) <= 16:
            return start, span // 8
    # suffix scan: longest valid run of records ending at header_size
    best = None
    for start in range(16, min(header_size, len(blob))):
        if (header_size - start) % 8:
            continue
        ok = True
        for position in range(start, header_size, 8):
            (record,) = struct.unpack_from("<Q", blob, position)
            kind = record >> 56
            size = (record >> 28) & 0x0FFFFFFF
            offset = record & 0x0FFFFFFF
            if kind not in KNOWN_TYPES or size == 0 or offset + size > len(blob):
                ok = False
                break
        if ok:
            length = (header_size - start) // 8
            if best is None or length > best[1]:
                best = (start, length)
    return best if best else (None, 0)


def census(blob):
    """Count streams, codecs and payload bytes in one container."""
    fields = header(blob)
    if fields is None:
        return None
    version, flags, count, header_size = fields
    start, records = chunk_table(blob, flags, count, header_size)
    if start is None:
        return {"flags": flags, "streams": count, "codecs": {}, "data": 0,
                "error": "no chunk table"}
    codecs = Counter()
    data_bytes = 0
    current = None
    for index in range(records):
        (record,) = struct.unpack_from("<Q", blob, start + 8 * index)
        kind = record >> 56
        size = (record >> 28) & 0x0FFFFFFF
        offset = record & 0x0FFFFFFF
        if kind == 0x55:
            current = 1
            data_bytes += size
        elif kind == 0x76 and size >= 32 and offset + 32 <= len(blob):
            codec = blob[offset + 0x1C]
            if current:
                codecs[codec] += 1
                current = None
    return {"flags": flags, "streams": count, "codecs": dict(codecs),
            "data": data_bytes, "error": ""}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--all", type=Path, required=True, help="full ADAT index")
    parser.add_argument("--known", type=Path, required=True,
                        help="extraction manifest of the containers already written")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--census", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    covered = set()
    with args.known.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            try:
                covered.add(int(row["start"], 16))
            except (KeyError, ValueError):
                continue
    rows = []
    with args.all.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            start, end = int(row["start"], 16), int(row["end"], 16)
            if start not in covered:
                rows.append((start, end))
    rows.sort()
    if args.limit:
        rows = rows[: args.limit]
    print(f"containers already extracted: {len(covered):,}")
    print(f"containers not covered by that pass: {len(rows):,} "
          f"({sum(e - s for s, e in rows):,} B)")

    census_rows = []
    totals = Counter()
    codecs = Counter()
    with args.archive.open("rb") as handle:
        for start, end in rows:
            handle.seek(start)
            blob = handle.read(end - start)
            result = census(blob)
            if result is None:
                totals["unparsed"] += 1
                continue
            totals["containers"] += 1
            totals["streams"] += result["streams"]
            totals["data_bytes"] += result["data"]
            for codec, count in result["codecs"].items():
                codecs[codec] += count
            census_rows.append((start, end, result))
            if args.out_dir:
                args.out_dir.mkdir(parents=True, exist_ok=True)
                (args.out_dir / f"{start:012x}.awc").write_bytes(blob)

    print(f"parsed {totals['containers']:,} containers, {totals['streams']:,} streams, "
          f"{totals['data_bytes']:,} B of stream data")
    if totals["unparsed"]:
        print(f"  unparsed: {totals['unparsed']}")
    print("  codecs:", ", ".join(f"0x{codec:02x}={count:,}"
                                 for codec, count in codecs.most_common(6)))
    if args.census:
        args.census.parent.mkdir(parents=True, exist_ok=True)
        with args.census.open("w") as handle:
            handle.write("start\tend\tflags\tstreams\tcodecs\tdata_bytes\terror\n")
            for start, end, result in census_rows:
                packed = ",".join(f"0x{codec:02x}:{count}"
                                  for codec, count in sorted(result["codecs"].items()))
                handle.write(f"0x{start:x}\t0x{end:x}\t0x{result['flags']:04x}\t"
                             f"{result['streams']}\t{packed}\t{result['data']}\t"
                             f"{result['error']}\n")
        print(f"  census -> {args.census}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
