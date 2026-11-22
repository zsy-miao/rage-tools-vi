"""Detect header plus 16-byte entry arrays in no-pointer object records."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import struct
import subprocess
import tempfile

OBJECT_START, OBJECT_END = 0x53000, 0xC3B45


def extract_object(cli, archive):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "object.bin"
        subprocess.run(
            [
                str(cli),
                "extract-zlib",
                str(archive),
                f"{OBJECT_START:x}",
                f"{OBJECT_END:x}",
                str(path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        return path.read_bytes()


def has_pointer(data, offset, size):
    for position in range(offset, offset + size - 7, 8):
        if struct.unpack_from("<I", data, position + 4)[0] == 0x71717171:
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--header", type=int, default=48)
    parser.add_argument("--size", type=int, default=176)
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    count = struct.unpack_from("<I", data, 0x14)[0]
    offsets = struct.unpack_from(f"<{count}Q", data, 0x28)

    layouts = Counter()
    examples = defaultdict(list)
    for index, offset in enumerate(offsets):
        end = offsets[index + 1] if index + 1 < count else len(data)
        size = end - offset
        if has_pointer(data, offset, size):
            continue
        for header in (16, 32, 48):
            if size > header and (size - header) % 16 == 0:
                entries = (size - header) // 16
                layouts[(size, header, entries)] += 1
                if len(examples[(size, header, entries)]) < 3:
                    examples[(size, header, entries)].append((index, offset))

    print("records with header + 16-byte entries")
    print("count\tsize\theader\tentries\texample_record\texample_offset")
    for (size, header, entries), total in layouts.most_common(40):
        example = examples[(size, header, entries)][0]
        print(f"{total}\t{size}\t{header}\t{entries}\t{example[0]}\t0x{example[1]:x}")

    key = None
    if args.size > args.header and (args.size - args.header) % 16 == 0:
        candidate = (args.size, args.header, (args.size - args.header) // 16)
        if candidate in layouts:
            key = candidate
    if key is None:
        key = next(
            ((size, header, entries) for (size, header, entries) in layouts if size == args.size),
            None,
        )
    if key is None:
        print(f"\nno layout for size {args.size}")
        return
    size, header, entries = key
    index, offset = examples[key][0]
    print(f"\nexample size {size}, header {header}, entries {entries}, record {index}")
    for position in range(0, min(size, header + 64), 16):
        chunk = data[offset + position : offset + position + 16]
        words = struct.unpack("<4I", chunk)
        floats = struct.unpack("<4f", chunk)
        print(
            f"  +0x{position:03x} {chunk.hex()} "
            f"u={[hex(word) for word in words]} f={['%.4g' % value for value in floats]}"
        )


if __name__ == "__main__":
    main()
