#!/usr/bin/env python3
"""Find complete raw DEFLATE streams in extracted RPF9 opaque ranges."""

import argparse
from collections import Counter
import csv
from hashlib import sha256
from pathlib import Path
import struct
import zlib

from extract_archive_ranges import classify


MAX_DECODED = 16 * 1024 * 1024


def probe(stored):
    decoder = zlib.decompressobj(-zlib.MAX_WBITS)
    try:
        decoded = decoder.decompress(stored, MAX_DECODED)
    except zlib.error:
        return None
    if not decoder.eof or len(decoded) < 16:
        return None
    return decoded, decoder.unused_data


def rbf_root(data):
    if not data.startswith(b"RBF0") or len(data) < 12:
        return ""
    size = struct.unpack_from("<H", data, 10)[0]
    name = data[12:12 + size]
    if len(name) == size and name.isalnum() and name.isascii():
        return name.decode("ascii")
    return ""


def inspect(directory):
    counts = Counter()
    with (directory / "ranges.tsv").open(newline="") as manifest:
        rows = list(csv.DictReader(manifest, delimiter="\t"))
    for row, following in zip(rows, rows[1:]):
        first = int(row["start"], 16)
        if row["kind"] != "unclassified" or first % 16 or int(row["stored_bytes"]) < 8:
            continue
        stored = (directory / row["file"]).read_bytes()
        pad = min(15, int(following["stored_bytes"])) if following["kind"] == "zero_run" else 0
        buffer = stored + bytes(pad)
        position = 0
        while position < len(stored):
            result = probe(buffer[position:])
            if result is None:
                break
            decoded, unused = result
            end = len(buffer) - len(unused)
            root = rbf_root(decoded)
            if (position or end != len(stored)) and not root:
                break
            extension, hint = classify(decoded)
            start = first + position
            path = f"raw-deflate/{start:08x}.{extension}"
            (directory / path).write_bytes(decoded)
            counts["exact" if position == 0 and end == len(stored) else "structured"] += 1
            counts["xml"] += extension == "xml"
            yield [f"{start:#x}", f"{first + end:#x}", end - position, len(decoded),
                   sha256(decoded).hexdigest(), path, f"RBF0:{root}" if root else hint,
                   row["start"], row["end"], max(0, end - len(stored))]
            next_position = (end + 15) & ~15
            if any(stored[end:next_position]):
                break
            position = next_position
    print(f"{directory.name}\t{counts['exact']}\t{counts['structured']}\t{counts['xml']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?", default=Path("output"))
    args = parser.parse_args()
    print("archive\texact_opaque_span\tstructured_raw_deflate_subranges\tcomplete_xml")
    for directory in sorted(args.output.glob("*.rpf")):
        if not (directory / "ranges.tsv").is_file():
            continue
        (directory / "raw-deflate").mkdir(exist_ok=True)
        with (directory / "raw-deflate.tsv").open("w", newline="") as report:
            writer = csv.writer(report, delimiter="\t", lineterminator="\n")
            writer.writerow(["start", "end", "stored_bytes", "decoded_bytes", "decoded_sha256",
                             "file", "format_hint", "opaque_span_start", "opaque_span_end",
                             "trailing_zero_bytes_consumed"])
            writer.writerows(inspect(directory))


if __name__ == "__main__":
    main()
