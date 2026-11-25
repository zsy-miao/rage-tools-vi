#!/usr/bin/env python3
"""Validate zlib candidates and weak DOS signatures in the extracted data.rpf."""

import argparse
from bisect import bisect_right
from collections import Counter
import csv
from hashlib import sha256
import mmap
from pathlib import Path
import re
import zlib

from data_rpf_inventory import SECTION_TAGS, psin_valid
from extract_archive_ranges import classify


MAX_DECODED = 16 * 1024 * 1024
ZLIB_START = re.compile(rb"\x78[\x01\x5e\x9c\xda]")


def read_table(path):
    with path.open(newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def decode(data, wbits, dictionary=b""):
    decoder = zlib.decompressobj(wbits, zdict=dictionary) if dictionary else zlib.decompressobj(wbits)
    try:
        decoded = decoder.decompress(data, MAX_DECODED + 1)
    except zlib.error as error:
        return None, 0, str(error).split(": ", 1)[-1]
    if len(decoded) > MAX_DECODED:
        return None, 0, "decoded size limit"
    if not decoder.eof:
        return None, 0, "no end-of-stream in available bytes"
    return decoded, len(data) - len(decoder.unused_data), ""


def prior_dictionary(directory, rows, index, start):
    index -= 1
    if rows[index]["kind"] == "zero_run":
        index -= 1
    prior = rows[index]
    if prior["kind"] != "zlib" or start != ((int(prior["end"], 16) + 15) & ~15):
        return b""
    size = int(prior["decoded_bytes"])
    length = min(size, 32768)
    with (directory / prior["file"]).open("rb") as source:
        source.seek(int(prior["file_offset"]) + size - length)
        return source.read(length)


def export_payload(directory, offset, decoded):
    extension, hint = classify(decoded)
    target = directory / "recovered-zlib" / f"{offset:06x}.{extension}"
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(decoded)
    return str(target.relative_to(directory)), hint


def audit_streams(directory, data, rows, labels):
    stats = Counter()
    with (directory / "opaque-streams.tsv").open("w", newline="") as report:
        writer = csv.writer(report, delimiter="\t", lineterminator="\n")
        writer.writerow([
            "start", "end", "source", "verification", "wrapped_error",
            "raw_error", "decoded_bytes", "decoded_sha256", "file", "format_hint",
        ])
        for index, row in enumerate(rows):
            if row["kind"] != "unclassified":
                continue
            start, end = int(row["start"], 16), int(row["end"], 16)
            padded_end = end
            if rows[index + 1]["kind"] == "zero_run":
                padded_end += min(15, int(rows[index + 1]["stored_bytes"]))
            for match in ZLIB_START.finditer(data, start, end):
                offset = match.start()
                anchored = offset == start and labels.get(row["file"], "").startswith("zlib")
                payload = data[offset:padded_end]
                decoded, consumed, wrapped_error = decode(payload, zlib.MAX_WBITS)
                raw_error = ""
                verification = "verified_zlib"
                if decoded is None and anchored:
                    decoded, consumed, raw_error = decode(payload[2:], -zlib.MAX_WBITS)
                    verification = "complete_deflate_without_matching_adler32"
                    if decoded is None and "distance too far back" in raw_error:
                        prior = prior_dictionary(directory, rows, index, offset)
                        if prior:
                            decoded, consumed, raw_error = decode(payload[2:], -zlib.MAX_WBITS, prior)
                    if decoded is not None:
                        consumed += 2
                        trailer = payload[consumed:consumed + 4]
                        if len(trailer) == 4 and zlib.adler32(decoded) == int.from_bytes(trailer, "big"):
                            consumed += 4
                            verification = "verified_adler32_with_previous_chunk_dictionary"
                if decoded is None and not anchored:
                    continue
                stats[verification if decoded is not None else wrapped_error] += 1
                file, hint = "", ""
                if verification.startswith("verified") and decoded is not None:
                    file, hint = export_payload(directory, offset, decoded)
                writer.writerow([
                    hex(offset), hex(offset + consumed) if consumed else "", row["file"],
                    verification if decoded is not None else "unverified", wrapped_error, raw_error,
                    len(decoded) if decoded is not None else "",
                    sha256(decoded).hexdigest() if decoded is not None else "", file, hint,
                ])
    return stats


def audit_dos(directory, rows, labels):
    groups = read_table(directory / "localized/groups.tsv")
    group_starts = [int(group["stored_start"], 16) for group in groups]
    decoded_rows = {
        row["file"]: (index, row) for index, row in enumerate(rows)
        if row["kind"] == "zlib" and row["file_offset"] == "0"
    }
    text_rows = {row["text_file"] for row in read_table(directory / "localized/text.tsv")}
    dos = Counter()
    with (directory / "dos-signatures.tsv").open("w", newline="") as report:
        writer = csv.writer(report, delimiter="\t", lineterminator="\n")
        writer.writerow(["file", "libmagic", "finding"])
        for file, label in labels.items():
            if not label.startswith("DOS"):
                continue
            finding = "unresolved_signature"
            if file in text_rows:
                (directory / file).read_text(encoding="utf-8")
                finding = "localized_utf8"
            elif file in decoded_rows:
                # These are compressed resource fragments when the stream
                # starts inside a verified multi-stream resource.
                row_index, row = decoded_rows[file]
                start = int(row["start"], 16)
                index = bisect_right(group_starts, start) - 1
                if index >= 0 and group_starts[index] < start < int(groups[index]["stored_end"], 16):
                    finding = "localized_resource_continuation"
                elif start % 0x1000 not in (0, 16):
                    if prior_dictionary(directory, rows, row_index, start):
                        finding = "aligned_continuation_after_verified_zlib"
                    else:
                        finding = "decoded_at_non_resource_start"
            dos[finding] += 1
            writer.writerow([file, label, finding])
    return dos


def psin_size_at(data, start, limit):
    cursor = start
    for tag in SECTION_TAGS:
        if cursor + 8 > limit or data[cursor:cursor + 4] != tag:
            return 0
        size = int.from_bytes(data[cursor + 4:cursor + 8], "big")
        if not 8 <= size <= limit - cursor:
            return 0
        cursor += size
    return cursor - start


def audit_stored_psin(directory, data, rows):
    with (directory / "stored-psin.tsv").open("w", newline="") as report:
        writer = csv.writer(report, delimiter="\t", lineterminator="\n")
        writer.writerow(["start", "end", "decoded_bytes", "sha256", "file"])
        count = 0
        for row in rows:
            if row["kind"] != "unclassified":
                continue
            start, end = int(row["start"], 16), int(row["end"], 16)
            cursor = start
            while (offset := data.find(b"PSIN", cursor, end)) >= 0:
                cursor = offset + 4
                if offset % 16:
                    continue
                size = psin_size_at(data, offset, end)
                if not size:
                    continue
                decoded = data[offset:offset + size]
                if not psin_valid(decoded):
                    continue
                output = directory / "stored-psin" / f"{offset:06x}.bin"
                output.parent.mkdir(exist_ok=True)
                output.write_bytes(decoded)
                writer.writerow([
                    hex(offset), hex(offset + size), size, sha256(decoded).hexdigest(),
                    str(output.relative_to(directory)),
                ])
                cursor = offset + size
                count += 1
    return count


def next_aligned_row(rows, index, end):
    if rows[index]["kind"] == "zero_run":
        index += 1
    row = rows[index]
    return index if int(row["start"], 16) == ((end + 15) & ~15) else None


def read_decoded_chunk(directory, row):
    with (directory / row["file"]).open("rb") as source:
        source.seek(int(row["file_offset"]))
        return source.read(int(row["decoded_bytes"]))


def complete_psin(data):
    size = psin_size_at(data, 0, len(data))
    return data[:size] if size and psin_valid(data[:size]) else None


def try_join_psin(directory, source, rows, last, initial):
    result = bytearray(initial)
    while last + 2 < len(rows):
        index = next_aligned_row(rows, last + 1, int(rows[last]["end"], 16))
        if index is None:
            return None
        row = rows[index]
        start, end = int(row["start"], 16), int(row["end"], 16)
        if row["kind"] == "zlib":
            chunk = read_decoded_chunk(directory, row)
            if chunk.startswith(b"PSIN"):
                return None
            result.extend(chunk)
            decoded = complete_psin(result)
            if decoded is not None and len(decoded) == len(result):
                return decoded, end
        elif row["kind"] == "unclassified":
            chunk = source[start:end]
            if ZLIB_START.match(chunk):
                return None
            terminal = complete_psin(result + chunk)
            if terminal is not None:
                return terminal, start + len(terminal) - len(result)
            if len(chunk) % 0x10000:
                return None
            result.extend(chunk)
        else:
            return None
        last = index
    return None


def audit_psin_joins(directory, source, rows):
    last_by_file = {row["file"]: index for index, row in enumerate(rows) if row["kind"] == "zlib"}
    count = 0
    with (directory / "rejoined-psin.tsv").open("w", newline="") as report:
        writer = csv.writer(report, delimiter="\t", lineterminator="\n")
        writer.writerow(["start", "end", "decoded_bytes", "sha256", "file"])
        for row in rows:
            if row["format_hint"] != "b'PSIN'":
                continue
            path = directory / row["file"]
            data = path.read_bytes()
            if psin_valid(data) or (directory / "mixed-psin" / path.name).is_file():
                continue
            joined = try_join_psin(directory, source, rows, last_by_file[row["file"]], data)
            if joined is None:
                continue
            decoded, end = joined
            output = directory / "rejoined-psin" / path.name
            output.parent.mkdir(exist_ok=True)
            output.write_bytes(decoded)
            writer.writerow([row["start"], hex(end), len(decoded), sha256(decoded).hexdigest(),
                             str(output.relative_to(directory))])
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("data.rpf"))
    parser.add_argument("--directory", type=Path, default=Path("output/data.rpf"))
    args = parser.parse_args()
    rows = read_table(args.directory / "ranges.tsv")
    labels = {row["file"]: row["libmagic"] for row in read_table(args.directory / "libmagic.tsv")}
    with args.archive.open("rb") as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
        print("zlib", dict(audit_streams(args.directory, data, rows, labels)))
        print("stored PSIN", audit_stored_psin(args.directory, data, rows))
        print("rejoined PSIN", audit_psin_joins(args.directory, data, rows))
    print("DOS", dict(audit_dos(args.directory, rows, labels)))


if __name__ == "__main__":
    main()
