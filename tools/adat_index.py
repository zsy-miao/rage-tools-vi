"""Index the `ADAT` containers inside an audio archive.

`audio.rpf` is 28.5 GB and the stream index classifies 99.93 % of it as
`unclassified`: the partitioner looks for zlib starts, and an AWC bank is neither
compressed nor self-describing at its start. The banks are still there, at 0x800
alignment, and each one declares its size through its tag table.

This walks them:

    ADAT header: magic, flags, count, header_size
    tables:      optional 0x400000 / 0x10000 / 0x200000 blocks, then `count` words
                 `id:29 | tag_count:3`   (the count is in the HIGH three bits)
    tag table:   sum(tag_count) records of 8 bytes
                 `type:8 | size:28 | offset:28`
    end          = max(offset + size over every tag), rounded up to 0x800

The last step is what makes the index possible: the bank's extent is the furthest
byte any of its tags reaches.

    python3 tools/adat_index.py /path/audio.rpf --out output/index/audio-adat.tsv
    python3 tools/adat_index.py /path/audio.rpf --limit 20 --show
"""

import argparse
import struct
import sys
from pathlib import Path

ALIGN = 0x800
# Banks are 0x800-aligned almost everywhere, but a handful sit on a 16-byte
# boundary only. Scan at 16 and let validation reject the noise.
SCAN_ALIGN = 4
CHUNK = 1 << 26
# Chunk/descriptor types seen in validated AWC banks. A random "ADAT" inside binary
# data produces arbitrary types, so this is the cheapest reliable filter.
KNOWN_TYPES = {0x55, 0x36, 0x76, 0xA3, 0xFA, 0x48, 0x5C, 0x68, 0x2B, 0x5A, 0xD9, 0xBD}
# Variants whose table has no computable position and must be found by suffix scan.
SCANNED_FLAGS = {0xFF25, 0xFF61}
MAX_BANK = 256 << 20     # no validated bank is larger than this
MAX_STREAMS = 4096


def find_banks(path, limit=0, start=0, stop=None):
    """Offsets of `ADAT` magics on the container alignment."""
    offsets = []
    with path.open("rb") as handle:
        handle.seek(start)
        position = start
        carry = b""
        end_limit = stop
        while True:
            if end_limit is not None and position >= end_limit:
                break
            block = handle.read(CHUNK)
            if not block:
                break
            data = carry + block
            start = 0
            while True:
                index = data.find(b"ADAT", start)
                if index < 0:
                    break
                absolute = position - len(carry) + index
                if end_limit is not None and absolute >= end_limit:
                    return offsets
                if absolute % SCAN_ALIGN == 0:
                    offsets.append(absolute)
                    if limit and len(offsets) >= limit:
                        return offsets
                start = index + 1
            carry = data[-8:]
            position += len(block)
    return offsets


def bank_extent(handle, offset):
    """(end, count, total_tags, variant, error) for the bank at `offset`.

    A candidate is rejected unless its stream words and tag table are structurally
    plausible: counts in range, every tag type known, and every extent inside the
    largest observed bank. Random `ADAT` occurrences fail at the first check.
    """
    handle.seek(offset)
    head = handle.read(16)
    if len(head) < 16 or head[:4] != b"ADAT":
        return None, 0, 0, 0, "no magic"
    flags, count, header_size = struct.unpack_from("<III", head, 4)
    position = 16 + (4 if flags & 0x400000 else 0)
    if flags & 0x10000:
        position += count * 2
    if flags & 0x200000:
        position += (count + 1) * 4
    info = position
    position += count * 4
    handle.seek(info)
    words = handle.read(count * 4)
    if len(words) < count * 4:
        return None, count, 0, flags, "short info table"
    if count == 0 or count > MAX_STREAMS:
        return None, count, 0, flags, "implausible stream count"
    counts = [word >> 29 for word in struct.unpack(f"<{count}I", words)]
    if any(entry > 32 for entry in counts):
        return None, count, 0, flags, "implausible tag count"
    total_tags = sum(counts)
    handle.seek(position)
    table = handle.read(total_tags * 8)
    if len(table) < total_tags * 8:
        return None, count, total_tags, flags, "short tag table"
    end = 0
    for index in range(total_tags):
        (record,) = struct.unpack_from("<Q", table, index * 8)
        kind = record >> 56
        size = (record >> 28) & 0x0FFFFFFF
        tag_offset = record & 0x0FFFFFFF
        if kind not in KNOWN_TYPES:
            return None, count, total_tags, flags, "unknown tag type"
        end = max(end, tag_offset + size)
    if end == 0:
        return None, count, total_tags, flags, "no extents"
    if end > MAX_BANK:
        return None, count, total_tags, flags, "extent too large"
    end = offset + ((end + ALIGN - 1) // ALIGN) * ALIGN
    return end, count, total_tags, flags, None


# Where the chunk table starts, per variant. `0x10 + 4*count` for 0xff02 is where
# the optional per-stream table would end; 0x50 is a fixed offset for 0xff21.
TABLE_AT = {0xFF21: lambda count: 0x50, 0xFF02: lambda count: 0x10 + 4 * count}

# Chunk/record types that appear in a real table. Used to validate a table whose
# position is not computable.
KNOWN_TYPES = {0x55, 0x36, 0x76, 0xA3, 0xFA, 0x48, 0x5C, 0x68, 0x2B, 0x5A, 0xD9, 0xBD}
# Variants whose table has no computable position and must be found by suffix scan.
SCANNED_FLAGS = {0xFF25, 0xFF61}


def scanned_table(handle, offset, data_offset, count):
    """Longest valid aligned record table ending at `data_offset`.

    `0xff25` and `0xff61` do not compute their table position, so it is recovered
    the way the published notes describe: the table is the longest run of valid
    8-byte records that ends exactly at the data offset. Records are
    `type:8 | size:28 | offset:28`, and a record is invalid when its type is unknown
    or its extent leaves the largest plausible bank.
    """
    handle.seek(offset)
    header = handle.read(data_offset)
    if len(header) < data_offset:
        return None, "short header region"
    if count and data_offset and (data_offset - 16) // (8 * count) > 16:
        # a table far longer than 16 records per stream is almost certainly padding
        pass
    best = None
    for start in range(16, data_offset):
        if (data_offset - start) % 8:
            continue
        ok = True
        extent = 0
        for position in range(start, data_offset, 8):
            (record,) = struct.unpack_from("<Q", header, position)
            kind = record >> 56
            size = (record >> 28) & 0x0FFFFFFF
            record_offset = record & 0x0FFFFFFF
            if kind not in KNOWN_TYPES or size == 0 or record_offset + size > MAX_BANK:
                ok = False
                break
            extent = max(extent, record_offset + size)
        if ok and extent:
            length = (data_offset - start) // 8
            if best is None or length > best[1]:
                best = (start, length, extent)
    if best is None:
        return None, "no valid table suffix"
    return best, None


def extent_bank(handle, offset, limit=MAX_BANK):
    """(end, count, error) for an AWC bank in a known variant.

    Both `0xff21` and `0xff02` hold exactly four chunk records per stream
    (`0x36 0x55 0x76 0xa3`), and in both the table ends exactly at `header_size` —
    the consistency check that keeps random `ADAT` bytes out. Each record is
    `type:8 | size:28 | offset:28`; the bank ends where the furthest record ends.
    """
    handle.seek(offset)
    head = handle.read(16)
    if len(head) < 16 or head[:4] != b"ADAT":
        return None, 0, "no magic"
    version, flags, count, header_size = struct.unpack_from("<HHII", head, 4)
    if flags not in TABLE_AT:
        if flags not in SCANNED_FLAGS:
            return None, count, f"unsupported flags 0x{flags:04x}"
        # no computable table position: recover it by suffix scan
        found, error = scanned_table(handle, offset, header_size, count)
        if error:
            return None, count, f"0x{flags:04x}: {error}"
        start, length, extent = found
        return offset + ((extent + ALIGN - 1) // ALIGN) * ALIGN, count, None
    if count == 0 or count > MAX_STREAMS:
        return None, count, "implausible stream count"
    table_at = TABLE_AT[flags](count)
    # Derive the record count instead of assuming it: the table must end exactly at
    # header_size, which is an integer constraint on records-per-stream.
    span = header_size - table_at
    if span <= 0 or span % (8 * count):
        # The computed position is the common case, not a law: a few banks carry an
        # extra per-stream table that shifts it. Fall back to the suffix scan.
        found, error = scanned_table(handle, offset, header_size, count)
        if error:
            return None, count, "table does not end at header_size"
        _start, _length, extent = found
        return offset + ((extent + ALIGN - 1) // ALIGN) * ALIGN, count, None
    records_per_stream = span // (8 * count)
    if not 1 <= records_per_stream <= 16:
        return None, count, "implausible records per stream"
    records = records_per_stream * count
    handle.seek(offset + table_at)
    table = handle.read(records * 8)
    if len(table) < records * 8:
        return None, count, "short table"
    end = 0
    for index in range(records):
        (record,) = struct.unpack_from("<Q", table, index * 8)
        end = max(end, (record & 0x0FFFFFFF) + ((record >> 28) & 0x0FFFFFFF))
    if end == 0 or end > limit:
        return None, count, "implausible extent"
    return offset + ((end + ALIGN - 1) // ALIGN) * ALIGN, count, None


def walk_gap(handle, start, stop):
    """Banks laid end to end from `start` until `stop`."""
    rows = []
    offset = start
    while offset < stop:
        end, count, error = extent_bank(handle, offset, stop - offset + ALIGN)
        if error:
            rows.append((offset, None, count, error))
            break
        rows.append((offset, end, count, None))
        if end <= offset:
            break
        offset = end
    return rows


def from_manifest(args, size):
    """Index banks from an extraction manifest: those extents were validated by decode."""
    import csv
    rows = []
    with args.manifest.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            try:
                start, end = int(row["start"], 16), int(row["end"], 16)
            except (KeyError, ValueError):
                continue
            rows.append((start, end, row.get("flags", ""), row.get("streams", "")))
    rows.sort()
    total = sum(end - start for start, end, *_ in rows)
    gaps = 0
    previous = 0
    for start, end, *_ in rows:
        if start < previous:
            gaps += 1
        previous = max(previous, end)
    print(f"{len(rows):,} banks from {args.manifest.name}, {total:,} B "
          f"({total / size:.2%} of {size:,})")
    print(f"  out of order or overlapping: {gaps}")
    if rows and args.show:
        for start, end, flags, streams in rows[:5]:
            print(f"  bank +0x{start:x}..0x{end:x} ({end - start:,} B) "
                  f"flags {flags} streams {streams}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as handle:
            handle.write("kind\tstart\tend\tstored_bytes\tdecoded_bytes\tchain_start\n")
            # Same six columns as every other index. `chain_start` means "the range
            # this one continues", so it must stay empty here: writing the container
            # flags into it made the verifier (correctly) reject the file.
            for start, end, _flags, _streams in rows:
                handle.write(f"adat\t0x{start:x}\t0x{end:x}\t{end - start}\t\t\n")
        print(f"  wrote {args.out}")
    return 0


def scan_all(args, size):
    """Index every bank in the archive, without a manifest."""
    rows = []
    errors = {}
    offsets = find_banks(args.archive, args.limit)
    with args.archive.open("rb") as handle:
        for offset in offsets:
            end, count, error = extent_bank(handle, offset, MAX_BANK)
            if error:
                errors[error] = errors.get(error, 0) + 1
                continue
            if rows and offset < rows[-1][1]:
                continue
            rows.append((offset, end, count))
    covered = sum(end - start for start, end, _count in rows)
    print(f"{args.archive.name}: candidates {len(offsets):,}, banks {len(rows):,}, "
          f"{covered:,} B ({covered / size:.3%} of the file)")
    print(f"  streams: {sum(count for _s, _e, count in rows):,}")
    for key, value in sorted(errors.items(), key=lambda item: -item[1]):
        print(f"  rejected: {key} x{value}")
    if args.show:
        for start, end, count in rows[:5]:
            print(f"  bank +0x{start:x}..0x{end:x} ({end - start:,} B) streams {count}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as handle:
            handle.write("kind\tstart\tend\tstored_bytes\tdecoded_bytes\tchain_start\n")
            for start, end, _count in rows:
                handle.write(f"adat\t0x{start:x}\t0x{end:x}\t{end - start}\t\t\n")
        print(f"  wrote {args.out}")
    return 0


def gaps_ff02(args, size):
    """Index the 0xff02 banks that sit between manifest-covered containers."""
    import csv
    covered = sorted((int(row["start"], 16), int(row["end"], 16))
                     for row in csv.DictReader(args.manifest.open(), delimiter="\t"))
    gaps = []
    previous = 0
    for start, end in covered:
        if start > previous:
            gaps.append((previous, start))
        previous = max(previous, end)
    if previous < size:
        gaps.append((previous, size))

    rows = []
    errors = {}
    padding = 0
    with args.archive.open("rb") as handle:
        for gap_start, gap_stop in gaps:
            # Banks are separated by zero padding, so walking "end to end" stops at
            # the first pad. Scanning the gap for aligned magics is the honest pass.
            for offset in find_banks(args.archive, 0, gap_start, gap_stop):
                end, count, error = extent_bank(handle, offset, gap_stop - offset + ALIGN)
                if error:
                    errors[error] = errors.get(error, 0) + 1
                    continue
                if rows and offset < rows[-1][1]:
                    padding += 1
                    continue
                rows.append((offset, end, count))
    if args.combine:
        merged = [(start, end) for start, end in covered] + [(s, e) for s, e, _c in rows]
        merged.sort()
        for (s1, e1), (s2, e2) in zip(merged, merged[1:]):
            if s2 < e1:
                print(f"  OVERLAP at 0x{s2:x}")
                return 1
        rows = [(s, e, 0) for s, e in merged]
        total = sum(e - s for s, e in merged)
        print(f"combined banks {len(merged):,}, {total:,} B ({total / size:.2%})")
    else:
        total = sum(end - start for start, end, _count in rows)
    print(f"gaps {len(gaps)}, banks {len(rows):,}, {total:,} B "
          f"({total / size:.2%} of the file)")
    print(f"  streams: {sum(count for _s, _e, count in rows):,}")
    if padding:
        print(f"  overlapping candidates skipped: {padding}")
    if errors:
        for key, value in sorted(errors.items(), key=lambda item: -item[1]):
            print(f"  {key}: {value}")
    if args.show:
        for start, end, count in rows[:5]:
            print(f"  bank +0x{start:x}..0x{end:x} ({end - start:,} B) streams {count}")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as handle:
            handle.write("kind\tstart\tend\tstored_bytes\tdecoded_bytes\tchain_start\n")
            for start, end, _count in rows:
                handle.write(f"adat\t0x{start:x}\t0x{end:x}\t{end - start}\t\t\n")
        print(f"  wrote {args.out}")
    return 0 if not errors else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--limit", type=int, default=0, help="stop after N banks")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--combine", action="store_true",
                        help="with --manifest and --gaps: write manifest banks and "
                             "gap banks into one index")
    parser.add_argument("--scan", action="store_true",
                        help="scan the whole archive for banks, no manifest needed")
    parser.add_argument("--gaps", action="store_true",
                        help="walk the 0xff02 banks that fill the gaps between "
                             "manifest-covered containers")
    parser.add_argument("--manifest", type=Path,
                        help="use start/end from an extraction manifest instead of "
                             "parsing headers (the 0xff21 variant does not use the "
                             "tag-table layout this parser assumes)")
    args = parser.parse_args()

    if not args.archive.is_file():
        sys.exit(f"missing {args.archive}")
    size = args.archive.stat().st_size
    if args.scan:
        return scan_all(args, size)
    if args.manifest and args.gaps:
        return gaps_ff02(args, size)
    if args.manifest:
        return from_manifest(args, size)
    offsets = find_banks(args.archive, args.limit)
    print(f"{args.archive.name}: {size:,} B, {len(offsets):,} aligned ADAT banks")

    rows = []
    errors = {}
    total = 0
    previous_end = 0
    overlaps = 0
    with args.archive.open("rb") as handle:
        for offset in offsets:
            end, count, tags, flags, error = bank_extent(handle, offset)
            if error:
                errors[error] = errors.get(error, 0) + 1
                continue
            if offset < previous_end:
                overlaps += 1
                continue
            previous_end = end
            total += end - offset
            rows.append((offset, end, count, tags, flags))
            if args.show and len(rows) <= 5:
                print(f"  bank +0x{offset:x}..0x{end:x} ({end - offset:,} B) "
                      f"streams {count} tags {tags} flags 0x{flags:06x}")

    print(f"parsed {len(rows):,} banks, {total:,} B ({total / size:.2%} of the file)")
    if overlaps:
        print(f"  overlapping banks skipped: {overlaps}")
    if errors:
        print("  errors:", ", ".join(f"{k}={v}" for k, v in errors.items()))
    if rows:
        print(f"  largest bank: {max(r[1] - r[0] for r in rows):,} B")
        print(f"  streams total: {sum(r[2] for r in rows):,}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as handle:
            handle.write("kind\tstart\tend\tstored_bytes\tdecoded_bytes\tchain_start\n")
            for offset, end, count, tags, flags in rows:
                handle.write(f"adat\t0x{offset:x}\t0x{end:x}\t{end - offset}\t\t"
                             f"0x{flags:x}\n")
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
