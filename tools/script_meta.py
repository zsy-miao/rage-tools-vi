"""Parse the script metadata resource by its writer's own rules.

The writer is `FUN_144083410` in the executable.  It emits a chain of chunks,
each `[4-byte magic][big-endian u32: distance to the next chunk]`, and nothing
in the chain is length-guessed: every size follows from a descriptor list and a
16-byte payload alignment, so a parse either fits exactly or is wrong.

Chunks, in the order the writer emits them:

  PSIN  property table
        +0x08: count x 16-byte descriptors `{u32 hash, u32 length, u64 0xAA..}`
               (the pointer field is poisoned with 0xAA on disk, which is why
               the earlier scans saw `0xAA` runs and read them as a terminator)
        then each descriptor's payload, appended in order, each 16-aligned.
        `count` is not stored: it is the unique value with
        `(16*count + 0x10) + sum(align16(length_i)) == next_chunk`
  LSCH  row table, `count` rows of 32 bytes; a row holds `u16 n` at +0x1e and a
        pointer at +0x10 to `n` 16-byte sub-records, appended in order
  LENM  `count` rows of 24 bytes; pointer at +0x08, `u16 n` at +0x10,
        sub-records of 16 bytes poisoned with 0xEE
  LSNS  table block, size given by `FUN_144080f60`
  LGID  `u32 count` then `count * 16` bytes
  LRSC  final 0x58-byte header block
  CHKS  optional trailer seen in `levels`-style records: `u32` big-endian record
        size, then a 4-byte tag we have not identified

The chunk header sizes are **big-endian** while the payload words are
little-endian, which is why `sections()` in `psin_extract.py` reading a
big-endian size happened to work.

  python3 tools/script_meta.py script.rpf --index output/index/script.tsv
  python3 tools/script_meta.py script.rpf --index output/index/script.tsv --dump 1
"""

import argparse
import csv
import struct
import sys
import zlib
from pathlib import Path

MAGICS = {b"PSIN": "PSIN", b"LSCH": "LSCH", b"LENM": "LENM",
          b"LSNS": "LSNS", b"LGID": "LGID", b"LRSC": "LRSC",
          b"CHKS": "CHKS"}
POISON = {0xAAAAAAAAAAAAAAAA, 0xEEEEEEEEEEEEEEEE, 0xBBBBBBBBBBBBBBBB}
TYPES = {0x101, 0x102, 0x103, 0x104, 0x105}


def align16(value):
    return (value + 15) & ~15


def chunk_header(body, offset):
    if offset + 8 > len(body):
        return None
    magic = body[offset:offset + 4]
    if magic not in MAGICS:
        return None
    return magic.decode(), struct.unpack_from(">I", body, offset + 4)[0]


def solve_count(body, offset, limit=512):
    """Find the descriptor count whose payload sum lands exactly on the next chunk."""
    head = chunk_header(body, offset)
    if head is None:
        return None
    _, rel = head
    for count in range(0, limit):
        # the writer rounds *down* here: (16*count + 0x17) & ~15 == 16*count + 0x10
        first = 16 * count + 0x10
        lengths = []
        good = True
        for index in range(count):
            if offset + 8 + 16 * index + 8 > len(body):
                good = False
                break
            length = struct.unpack_from("<I", body, offset + 8 + 16 * index + 4)[0]
            if length > 0x100000:
                good = False
                break
            lengths.append(length)
        if not good:
            continue
        if first + sum(align16(length) for length in lengths) == rel:
            return count, first, lengths
    return None


def parse_psin(body, offset, dump=0):
    solved = solve_count(body, offset)
    if solved is None:
        return None
    count, first, lengths = solved
    descriptors = []
    for index in range(count):
        base = offset + 8 + 16 * index
        key, length = struct.unpack_from("<II", body, base)
        pointer = struct.unpack_from("<Q", body, base + 8)[0]
        descriptors.append({"key": key, "length": length, "pointer": pointer})
    cursor = offset + first
    rows = []
    for descriptor in descriptors:
        descriptor["payload"] = offset + (cursor - offset)
        if dump:
            for position in range(0, descriptor["length"] - 15, 16):
                value, kind, prop, field = struct.unpack_from("<IIII", body, cursor + position)
                rows.append((descriptor["key"], value, kind, prop, field))
        cursor += align16(descriptor["length"])
    return {"count": count, "first_payload": first, "descriptors": descriptors, "rows": rows}


def solve_rows(body, offset, stride, sub_field, limit=512):
    """Row count whose rows plus aligned sub-records land on the next chunk."""
    header = chunk_header(body, offset)
    if header is None:
        return None
    _, rel = header
    for count in range(0, limit):
        subcounts = []
        good = True
        for index in range(count):
            base = offset + 8 + stride * index + sub_field
            if base + 2 > len(body):
                good = False
                break
            subcounts.append(struct.unpack_from("<H", body, base)[0])
        if not good:
            continue
        total = 8 + stride * count + sum(align16(16 * sub) for sub in subcounts)
        if total == rel:
            return count, subcounts
    return None


def parse_rows(body, offset, stride, pointer_field, sub_field):
    solved = solve_rows(body, offset, stride, sub_field)
    if solved is None:
        return None
    count, subcounts = solved
    rows = []
    for index in range(count):
        base = offset + 8 + stride * index
        pointer = struct.unpack_from("<Q", body, base + pointer_field)[0]
        rows.append({"pointer": pointer, "subcount": subcounts[index]})
    return {"count": count, "rows": rows, "subrecords": sum(subcounts)}


def walk(body):
    """Follow the chunk chain; return the chunk list and per-chunk detail."""
    chunks = []
    offset = 0
    for _ in range(16):
        header = chunk_header(body, offset)
        if header is None:
            break
        magic, rel = header
        chunk = {"magic": magic, "offset": offset, "next": rel}
        if magic == "PSIN":
            parsed = parse_psin(body, offset)
            if parsed:
                chunk.update(count=parsed["count"], descriptors=parsed["descriptors"])
                chunk["row_bytes"] = sum(d["length"] for d in parsed["descriptors"])
        elif magic == "LSCH":
            parsed = parse_rows(body, offset, 32, 0x10, 0x1E)
            if parsed:
                chunk.update(parsed)
        elif magic == "LENM":
            parsed = parse_rows(body, offset, 24, 0x08, 0x10)
            if parsed:
                chunk.update(parsed)
        elif magic == "LSNS":
            chunk["payload"] = rel - 8
        elif magic == "LGID":
            # the writer omits the payload entirely when the list is absent
            count = struct.unpack_from("<I", body, offset + 8)[0] if offset + 12 <= len(body) else 0
            chunk["count"] = count
            if rel == 8:
                chunk["count"] = 0
            elif 8 + 4 + count * 16 != rel:
                chunk["count"] = None
        chunks.append(chunk)
        if rel == 0 or offset + rel >= len(body):
            break
        offset += rel
    return chunks


def _decompress(handle, start, end):
    handle.seek(start)
    return zlib.decompress(handle.read(end - start))


def streams(archive, index):
    """Yield (record index, body) for every zlib stream whose body starts with PSIN.

    Reads each range with seek/read rather than loading the archive: `levels.rpf`
    alone is far larger than memory.
    """
    ranges = sorted((int(row["start"], 16), int(row["end"], 16))
                    for row in csv.DictReader(index.open(), delimiter="\t")
                    if row["kind"] == "zlib")
    with archive.open("rb") as handle:
        for position, (start, end) in enumerate(ranges):
            try:
                body = _decompress(handle, start, end)
            except (zlib.error, MemoryError):
                continue
            if not body.startswith(b"PSIN"):
                continue
            if len(body) == 65536 and position + 1 < len(ranges):
                next_start, next_end = ranges[position + 1]
                try:
                    body += _decompress(handle, next_start, next_end)
                except (zlib.error, MemoryError):
                    pass
            yield position, body


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--index", type=Path, default=Path("output/index/script.tsv"))
    parser.add_argument("--dump", type=int, default=0, help="rows to print per record")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--verify", action="store_true",
                        help="require the chain to cover each body exactly")
    args = parser.parse_args()

    if not args.archive.is_file():
        sys.exit(f"missing archive {args.archive}")
    if not args.index.is_file():
        sys.exit(f"missing index {args.index}")

    total = 0
    complete = 0
    exact = 0
    slack = {}
    chunk_counts = {}
    dumped = 0
    problem = []
    for position, body in streams(args.archive, args.index):
        if args.limit and total >= args.limit:
            break
        total += 1
        chunks = walk(body)
        names = [chunk["magic"] for chunk in chunks]
        for name in names:
            chunk_counts[name] = chunk_counts.get(name, 0) + 1
        # `script.rpf` stops at LRSC; `levels`-style records append a CHKS trailer
        expected = ["PSIN", "LSCH", "LENM", "LSNS", "LGID", "LRSC"]
        if names == expected or names == expected + ["CHKS"]:
            complete += 1
        if chunks:
            end = chunks[-1]["offset"] + chunks[-1]["next"]
            if end == len(body):
                exact += 1
            else:
                slack[len(body) - end] = slack.get(len(body) - end, 0) + 1
        elif len(problem) < 6:
            problem.append((position, names))
        if args.dump and dumped < args.dump:
            dumped += 1
            print(f"\nrecord {position}  body {len(body)} B")
            for chunk in chunks:
                extra = ""
                if "count" in chunk:
                    extra = f" count={chunk['count']}"
                    if "row_bytes" in chunk:
                        extra += f" payload={chunk['row_bytes']} B"
                print(f"  {chunk['magic']}  +0x{chunk['offset']:04x}  next +0x{chunk['next']:04x}{extra}")
                for descriptor in chunk.get("descriptors", [])[:6]:
                    print(f"      hash 0x{descriptor['key']:08x} len {descriptor['length']:6d} "
                          f"ptr 0x{descriptor['pointer']:016x}")
            parsed = parse_psin(body, 0, dump=1)
            if parsed and parsed["rows"]:
                for key, value, kind, prop, field in parsed["rows"][:12]:
                    print(f"      row hash 0x{key:08x}  value 0x{value:08x} type 0x{kind:03x} "
                          f"prop 0x{prop:08x} field 0x{field:08x}")

    print(f"\nrecords: {total}  full PSIN→LRSC chain: {complete}")
    print(f"chain covers the body exactly: {exact}/{total}")
    if slack:
        print("slack (body length minus chain end):",
              ", ".join(f"{value:+d}×{count}" for value, count in
                        sorted(slack.items(), key=lambda item: -item[1])[:6]))
        if args.verify:
            return 1
    print("chunks seen:", ", ".join(f"{name}={count}" for name, count in
                                    sorted(chunk_counts.items(), key=lambda kv: -kv[1])))
    if problem:
        print("incomplete chains (first six):")
        for position, names in problem:
            print(f"  record {position}: {' '.join(names) or '(none)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
