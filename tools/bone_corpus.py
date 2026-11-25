"""Match plaintext data.rpf PSIN bone names against the script.rpf object tree."""

import argparse
from collections import Counter
from pathlib import Path
import re
import struct
import subprocess
import tempfile

OBJECT_START, OBJECT_END = 0x53000, 0xC3B45


def joaat(text):
    value = 0
    for byte in text.encode():
        value = (value + byte) & 0xFFFFFFFF
        value = (value + (value << 10)) & 0xFFFFFFFF
        value ^= value >> 6
    value = (value + (value << 3)) & 0xFFFFFFFF
    value ^= value >> 11
    value = (value + (value << 15)) & 0xFFFFFFFF
    return value & 0xFFFFFFFF


def harvest(data_dir):
    names = set()
    files = 0
    for path in data_dir.glob("*.bin"):
        data = path.read_bytes()
        if not data.startswith(b"PSIN"):
            continue
        files += 1
        size = struct.unpack_from(">I", data, 4)[0]
        body = data[8:size]
        for part in body.split(b"\0"):
            if re.fullmatch(rb"[A-Za-z_][A-Za-z0-9_]{2,}", part):
                names.add(part.decode())
    return files, names


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
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("output/data.rpf/decoded"),
    )
    parser.add_argument("--names-file", type=Path)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()

    if args.names_file:
        names = {line.strip() for line in args.names_file.read_text().splitlines() if line.strip()}
        files = None
    else:
        files, names = harvest(args.data_dir)
    lookup = {}
    for name in names:
        for variant in {name, name.lower()}:
            lookup.setdefault(joaat(variant), set()).add(variant)
    data = extract_object(args.cli, args.archive)
    hits = []
    for position in range(0, len(data) - 3, 4):
        value = struct.unpack_from("<I", data, position)[0]
        if value in lookup:
            hits.append((position, value, sorted(lookup[value])))
    expected = len(data) // 4 * len(lookup) / 2**32
    print(f"source files: {files if files is not None else 'names file'}")
    print(f"unique names: {len(names)}, hashes: {len(lookup)}")
    print(f"hits: {len(hits)}, expected random: {expected:.2f}")
    print("top names:")
    for name, count in Counter(name for _, _, labels in hits for name in labels).most_common(args.limit):
        print(f"  {count:5} {name}")
    print("sample hits:")
    for position, value, labels in hits[: args.limit]:
        print(f"  0x{position:x} 0x{value:08x} {','.join(labels[:3])}")


if __name__ == "__main__":
    main()
