"""Dump a named object subtree from the script.rpf object graph."""

import argparse
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from root_names import candidates, joaat  # noqa: E402

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?", help="root or part name, for example airbus")
    parser.add_argument("--id", type=lambda value: int(value, 0), help="root hash as a number")
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    count = struct.unpack_from("<I", data, 0x14)[0]
    offsets = struct.unpack_from(f"<{count}Q", data, 0x28)
    by_address = {offset + 8: index for index, offset in enumerate(offsets)}
    lookup = {}
    for name in candidates(Path("."), True):
        for variant in {name, name.lower()}:
            lookup.setdefault(joaat(variant), set()).add(variant)

    def end(index):
        return offsets[index + 1] if index + 1 < count else len(data)

    def name_at(index, field):
        if offsets[index] + field + 4 > end(index):
            return None
        value = struct.unpack_from("<I", data, offsets[index] + field)[0]
        labels = lookup.get(value)
        return sorted(labels)[0] if labels else None

    def pointers(index):
        result = []
        for position in range(offsets[index], end(index) - 7, 8):
            address, tag = struct.unpack_from("<II", data, position)
            if tag == 0x71717171 and address in by_address:
                result.append((position - offsets[index], by_address[address]))
        return result

    def dump(index, depth=0, seen=None):
        if seen is None:
            seen = set()
        if index in seen or depth > args.depth:
            return
        seen.add(index)
        offset = offsets[index]
        size = end(index) - offset
        labels = name_at(index, 0) or name_at(index, 0x10) or ""
        links = pointers(index)
        print(
            f'{"  " * depth}rec {index} off 0x{offset:x} size {size} '
            f"name={labels} links={[(hex(field), target) for field, target in links]}"
        )

        header = struct.unpack_from("<11I", data, offset) if size >= 44 else ()
        printed = False
        if size >= 48 and not links:
            entry_size = header[6] if len(header) > 6 else 0
            entries = header[4] if len(header) > 4 else 0
            if entry_size in (8, 16, 48) and size >= 48 + entries * entry_size:
                print(
                    f'{"  " * (depth + 1)}array entries={entries} '
                    f"entry_size={entry_size} type=0x{header[10]:08x}"
                )
                printed = True
                for entry in range(min(entries, 4)):
                    position = offset + 48 + entry * entry_size
                    if entry_size == 8:
                        address = struct.unpack_from("<I", data, position)[0]
                        target = by_address.get(address)
                        print(f'{"  " * (depth + 2)}entry {entry}: ptr {target}')
                    else:
                        chunk = data[position : position + entry_size]
                        values = struct.unpack(f"<{entry_size // 4}f", chunk)
                        print(
                            f'{"  " * (depth + 2)}entry {entry}: {chunk.hex()} '
                            f'f={["%.4g" % value for value in values]}'
                        )
        if not links and not printed and size >= 16:
            chunk = data[offset : offset + min(size, 32)]
            values = struct.unpack("<4f", data[offset + 8 : offset + 24]) if size >= 24 else ()
            print(f'{"  " * (depth + 1)}data {chunk.hex()} f@8={["%.4g" % value for value in values]}')

        for _, target in links[: args.limit]:
            dump(target, depth + 1, seen)

    found = None
    for index in range(count):
        identifier = struct.unpack_from("<I", data, offsets[index])[0]
        if args.id is not None:
            if identifier == args.id:
                found = index
                break
        elif args.name in (name_at(index, 0), name_at(index, 0x10)):
            found = index
            break
    if found is None:
        target = f"0x{args.id:08x}" if args.id is not None else args.name
        raise SystemExit(f"name or id not found: {target}")
    dump(found)


if __name__ == "__main__":
    main()
