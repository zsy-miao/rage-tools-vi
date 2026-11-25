#!/usr/bin/env python3
"""Identify opaque RPF9 fragments from verified neighboring payload headers."""

import argparse
from bisect import bisect_right
from collections import Counter
import csv
from pathlib import Path
import re
import struct

from audit_opaque_streams import read_table
from data_rpf_inventory import PSIN_SECTION_LAYOUTS, SECTION_TAGS


def section_at_boundary(path, length):
    """Walk section headers only and locate the first missing decoded byte."""
    cursor = 0
    with path.open("rb") as source:
        for expected in SECTION_TAGS:
            if cursor + 8 > length:
                return f"{expected.decode()}_header"
            source.seek(cursor)
            tag, size = struct.unpack(">4sI", source.read(8))
            if tag != expected or size < 8:
                return "section_sequence_mismatch"
            cursor += size
            if cursor > length:
                return tag.decode()
    return "past_CHKS" if length > cursor else "complete_boundary"


def previous_stream(rows, index):
    start = int(rows[index]["start"], 16)
    index -= 1
    if rows[index]["kind"] == "zero_run":
        index -= 1
    row = rows[index]
    if row["kind"] == "zlib" and start == ((int(row["end"], 16) + 15) & ~15):
        return row
    return None


def identify_prefix(path, length):
    with path.open("rb") as source:
        header = source.read(24)
    if header.startswith(b"PSIN"):
        return "PSIN", section_at_boundary(path, length)
    if header[16:21] == b"0DRPz":
        return "0DRPz at decoded +0x10", ""
    for tag in (b"RBF0", b"HMAP", b"SPS1", b"MHUI", b"9FPR", b"RIFF", b"OggS", b"DDS "):
        if header.startswith(tag):
            return tag.decode(), ""
    if len(header) >= 16:
        first, second = struct.unpack_from("<QQ", header)
        if any(0x50000000 <= word < 0x60000000 for word in (first, second)):
            return "RAGE virtual pointer at decoded +0x00 or +0x08", ""
    return "unknown", ""


def audit_opaque(directory, rows):
    starts = {int(row["start"], 16): index for index, row in enumerate(rows)}
    headers = [int(row["header_offset"], 16) for row in read_table(directory / "packs.tsv")]
    candidates = read_table(directory / "opaque-streams.tsv")
    dos = read_table(directory / "dos-signatures.tsv")
    opaque_files = {row["file"]: row for row in rows if row["kind"] == "unclassified"}
    candidates.extend(
        {"start": opaque_files[row["file"]]["start"], "source": row["file"]}
        for row in dos if row["finding"] == "unresolved_signature" and row["file"] in opaque_files
    )
    counts = Counter()
    nearest = Counter()
    with (directory / "opaque-context.tsv").open("w", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow([
            "start", "file", "nearest_header", "preceding_verified_chain", "preceding_decoded_bytes",
            "object_header", "section_at_boundary",
        ])
        for candidate in candidates:
            start = int(candidate["start"], 16)
            header = headers[bisect_right(headers, start) - 1]
            prior = previous_stream(rows, starts[start]) if start in starts else None
            object_header, section = "no adjacent verified prefix", ""
            length = 0
            if prior:
                length = int(prior["file_offset"]) + int(prior["decoded_bytes"])
                object_header, section = identify_prefix(directory / prior["file"], length)
            counts[(object_header, section)] += 1
            nearest[hex(header)] += 1
            writer.writerow([
                hex(start), candidate["source"], hex(header), prior["chain_start"] if prior else "",
                length or "", object_header, section,
            ])
    return counts, nearest


def audit_open_psin(directory, rows):
    counts = Counter()
    layouts = Counter()
    known_layouts = {tuple(tag.decode() for tag in layout) for layout in PSIN_SECTION_LAYOUTS}
    with (directory / "psin-layouts.tsv").open("w", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(["start", "file", "decoded_bytes", "section_sequence", "validation"])
        for row in rows:
            if row["format_hint"] != "b'PSIN'":
                continue
            path = directory / row["file"]
            length = path.stat().st_size
            tags, complete = actual_sections(path, length)
            section = "valid" if complete and tags in known_layouts else "unverified"
            counts[section] += 1
            layouts[(tags, complete)] += 1
            writer.writerow([row["start"], row["file"], length, " ".join(tags), section])
    return counts, layouts


def actual_sections(path, length):
    tags = []
    cursor = 0
    with path.open("rb") as source:
        while cursor + 8 <= length:
            source.seek(cursor)
            tag, size = struct.unpack(">4sI", source.read(8))
            if not re.fullmatch(rb"[A-Z]{4}", tag) or size < 8:
                break
            tags.append(tag.decode())
            if tag == b"CHKS":
                if size >= 12 and cursor + size == length:
                    return tuple(tags), int.from_bytes(source.read(4), "big") == length
                break
            if cursor + size > length:
                break
            cursor += size
    return tuple(tags), False


def audit_payload_headers(directory):
    counts = Counter()
    roots = Counter()
    with (directory / "payload-headers.tsv").open("w", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(["file", "header", "root_type"])
        for folder in ("decoded", "raw-deflate"):
            for path in sorted((directory / folder).iterdir()):
                with path.open("rb") as source:
                    header = source.read(128)
                if header.startswith(b"RBF0\xfb\xff") and len(header) >= 12:
                    size = struct.unpack_from("<H", header, 10)[0]
                    name = header[12:12 + size]
                    if len(name) == size and re.fullmatch(rb"[A-Za-z_][A-Za-z0-9_]*", name):
                        root = name.decode()
                        roots[(folder, root)] += 1
                        counts[(folder, "RBF0")] += 1
                        writer.writerow([path.relative_to(directory), "RBF0", root])
                    continue
                if header[16:21] == b"0DRPz":
                    counts[(folder, "0DRPz")] += 1
                    writer.writerow([path.relative_to(directory), "0DRPz at decoded +0x10", ""])
    return counts, roots


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="?", default=Path("output/data.rpf"))
    args = parser.parse_args()
    rows = read_table(args.directory / "ranges.tsv")
    counts, nearest = audit_opaque(args.directory, rows)
    print("Opaque candidates by adjacent object and boundary:")
    for (header, section), count in counts.most_common():
        print(count, header, section, sep="\t")
    print("Nearest archive headers:", dict(nearest))
    psin, layouts = audit_open_psin(args.directory, rows)
    print("PSIN default chains by structural validation:", dict(psin))
    for (layout, complete), count in layouts.most_common():
        print("PSIN layout", count, " ".join(layout), f"CHKS length matches={complete}", sep="\t")
    headers, roots = audit_payload_headers(args.directory)
    print("Additional payload headers:", dict(headers))
    for (folder, root), count in roots.most_common(20):
        print("RBF0 root", folder, count, root, sep="\t")


if __name__ == "__main__":
    main()
