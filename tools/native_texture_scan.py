"""Scan decoded data.rpf resources for native texture dictionaries."""

import argparse
import csv
from hashlib import sha256
from pathlib import Path
import re
import struct
import zlib

FORMAT_STRIDES = {0x47: 8, 0x4D: 16, 0x62: 16}


def read_rows(path):
    with path.open(newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


def inflate(source, start, end):
    source.seek(start)
    stored = source.read(end - start)
    decoder = zlib.decompressobj()
    decoded = decoder.decompress(stored)
    if not decoder.eof or decoder.unused_data or len(stored) != end - start:
        raise ValueError(f"stored range {start:#x}..{end:#x} is not one exact zlib stream")
    return decoded


def joaat(text):
    value = 0
    for char in text.lower().encode():
        value = (value + char) & 0xFFFFFFFF
        value = (value + (value << 10)) & 0xFFFFFFFF
        value ^= value >> 6
    value = (value + (value << 3)) & 0xFFFFFFFF
    value ^= value >> 11
    return (value + (value << 15)) & 0xFFFFFFFF


def virtual_offset(pointer, base, size, length):
    offset = pointer - base
    if not 0 <= offset <= size - length:
        raise ValueError(f"invalid virtual pointer {pointer:#x} for {base:#x}+{size:#x}")
    return offset


def texture_dictionary(system, graphics):
    hashes, hash_count, hash_capacity = struct.unpack_from("<QHH", system, 0x20)
    pointers, count, capacity = struct.unpack_from("<QHH", system, 0x30)
    if not 0 < count == capacity == hash_count == hash_capacity:
        raise ValueError("texture pointer and hash arrays disagree")
    hash_offset = virtual_offset(hashes, 0x50000000, len(system), count * 4)
    pointer_offset = virtual_offset(pointers, 0x50000000, len(system), count * 8)
    records = []
    for index in range(count):
        pointer = struct.unpack_from("<Q", system, pointer_offset + index * 8)[0]
        descriptor = virtual_offset(pointer, 0x50000000, len(system), 0x40)
        blocks, stride, kind, flags, address = struct.unpack_from("<IHHQQ", system, descriptor + 8)
        width, height, depth = struct.unpack_from("<HHH", system, descriptor + 0x38)
        format_code = system[descriptor + 0x3F]
        if not blocks or (kind, flags) != (8, 0x980) or stride != FORMAT_STRIDES.get(format_code):
            raise ValueError(
                f"unexpected descriptor at {descriptor:#x}, format {format_code:#x}, stride {stride}"
            )
        if not width or not height or depth != 1:
            raise ValueError(f"invalid surface dimensions at {descriptor:#x}")
        name_address = struct.unpack_from("<Q", system, descriptor + 0x30)[0]
        name_offset = virtual_offset(name_address, 0x50000000, len(system), 9) + 8
        name = system[name_offset:].split(b"\0", 1)[0]
        if not re.fullmatch(rb"[a-z][a-z0-9_]*", name):
            raise ValueError(f"invalid texture name at {name_offset:#x}")
        expected_hash = struct.unpack_from("<I", system, hash_offset + index * 4)[0]
        if joaat(name.decode()) != expected_hash:
            raise ValueError(f"name hash mismatch for {name!r}")
        size = blocks * stride
        start = virtual_offset(address, 0x60000000, len(graphics), size)
        records.append((name.decode(), expected_hash, descriptor, width, height, format_code, start, size))
    cursor = 0
    for start, size in sorted((record[-2], record[-1]) for record in records):
        if start < cursor:
            raise ValueError("overlapping texture buffers")
        cursor = start + size
    if any(graphics[cursor:]):
        raise ValueError(f"nonzero bytes beyond last texture extent: {cursor:#x} of {len(graphics):#x}")
    return records


def control_group(rows, index):
    group = []
    end = int(rows[index]["start"], 16)
    while index < len(rows):
        row = rows[index]
        if row["kind"] == "zero_run":
            index += 1
            continue
        if row["kind"] != "zlib" or int(row["start"], 16) != ((end + 15) & ~15):
            break
        group.append(row)
        end = int(row["end"], 16)
        index += 1
    if len(group) < 2:
        raise ValueError("missing graphics streams for texture dictionary")
    return group


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path, nargs="?", default=Path("."))
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--decoded", type=Path)
    parser.add_argument("--extract-to", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    archive = args.archive or args.repository / "data.rpf"
    decoded = args.decoded or args.repository / "output/data.rpf/decoded"
    destination = args.extract_to or args.repository / "output/data.rpf/textures-expanded"
    rows = read_rows(args.repository / "output/data.rpf/ranges.tsv")
    by_start = {int(row["start"], 16): index for index, row in enumerate(rows) if row["kind"] == "zlib"}

    candidates = []
    for path in decoded.glob("*.bin"):
        if len(path.stem) != 8:
            continue
        try:
            start = int(path.stem, 16)
        except ValueError:
            continue
        with path.open("rb") as handle:
            header = handle.read(0x50)
        if len(header) < 0x50:
            continue
        try:
            hashes, hash_count, hash_capacity = struct.unpack_from("<QHH", header, 0x20)
            pointers, count, capacity = struct.unpack_from("<QHH", header, 0x30)
        except struct.error:
            continue
        if (
            0 < hash_count == hash_capacity == count == capacity
            and hashes >> 28 == 5
            and pointers >> 28 == 5
        ):
            candidates.append((start, path.name))

    if not args.dry_run:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "files").mkdir(exist_ok=True)

    manifest = []
    total_bytes = 0
    valid = 0
    failed = 0
    with archive.open("rb") as source:
        for start, name in candidates:
            index = by_start.get(start)
            if index is None:
                failed += 1
                continue
            try:
                group = control_group(rows, index)
                streams = [inflate(source, int(row["start"], 16), int(row["end"], 16)) for row in group]
                system, graphics = streams[0], b"".join(streams[1:])
                records = texture_dictionary(system, graphics)
            except ValueError:
                failed += 1
                continue
            valid += 1
            stored = ",".join(f"{row['start']}..{row['end']}" for row in group)
            for texture_name, texture_hash, descriptor, width, height, format_code, offset, size in records:
                data = graphics[offset : offset + size]
                total_bytes += size
                file_name = f"{start:08x}-{texture_name}.bin"
                if not args.dry_run:
                    (destination / "files" / file_name).write_bytes(data)
                manifest.append(
                    [
                        name,
                        texture_name,
                        hex(texture_hash),
                        hex(start),
                        group[-1]["end"],
                        stored,
                        hex(descriptor),
                        width,
                        height,
                        hex(format_code),
                        hex(len(system) + offset),
                        size,
                        sha256(data).hexdigest(),
                        file_name,
                    ]
                )

    if not args.dry_run:
        with (destination / "manifest.tsv").open("w", newline="") as output:
            writer = csv.writer(output, delimiter="\t", lineterminator="\n")
            writer.writerow(
                [
                    "dictionary",
                    "name",
                    "joaat",
                    "archive_start",
                    "archive_end",
                    "stored_zlib_ranges",
                    "descriptor_offset",
                    "width",
                    "height",
                    "format_code",
                    "decoded_offset",
                    "bytes",
                    "sha256",
                    "file",
                ]
            )
            writer.writerows(manifest)

    print(f"candidates: {len(candidates)}")
    print(f"valid dictionaries: {valid}, failed: {failed}")
    print(f"textures: {len(manifest)}, bytes: {total_bytes}")
    print(f"destination: {destination}")


if __name__ == "__main__":
    main()
