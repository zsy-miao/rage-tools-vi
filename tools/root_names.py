"""Match the script.rpf object-tree root IDs against JOAAT names."""

import argparse
import re
from pathlib import Path
import struct
import subprocess
import tempfile

OBJECT_START, OBJECT_END = 0x53000, 0xC3B45

# Vehicle names not present in the extracted XML.
CURATED = {
    "car_hydraulics",
    "baller7",
    "Buzzard2",
    "rumpo3",
    "police3",
    "sheriff2",
    "firetruk",
    "everon",
    "dominator3",
    "Sadler",
    "italigto",
    "blazer2",
}


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


def parse_roots(data):
    count = struct.unpack_from("<I", data, 0x14)[0]
    offsets = struct.unpack_from(f"<{count}Q", data, 0x28)
    targets = set()
    for position in range(0, len(data) - 7, 8):
        address, tag = struct.unpack_from("<II", data, position)
        if tag == 0x71717171:
            targets.add(address)
    roots = []
    for offset in offsets:
        identifier = struct.unpack_from("<I", data, offset)[0]
        if identifier and offset + 8 not in targets:
            roots.append(identifier)
    return roots


def candidates(archive_dir, use_wordlist):
    result = set(CURATED)
    for path in (archive_dir / "output").rglob("*.xml"):
        text = path.read_text(errors="ignore")
        tokens = set(re.findall(r"[A-Za-z0-9_.-]+", text))
        result |= tokens
        for token in tokens:
            for part in re.split(r"[._/-]+", token):
                if len(part) >= 2:
                    result.add(part)
    if use_wordlist:
        path = Path("/usr/share/dict/words")
        if path.is_file():
            result |= {line.strip() for line in path.read_text(errors="ignore").splitlines() if line.strip()}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--archive-dir", type=Path, default=Path("."))
    parser.add_argument("--no-wordlist", action="store_true")
    parser.add_argument("--extra", type=Path, action="append", default=[], help="name=hash or plain name list")
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    roots = parse_roots(data)
    names = candidates(args.archive_dir, not args.no_wordlist)
    mapping = {}
    for name in names:
        for variant in {name, name.lower()}:
            identifier = joaat(variant)
            if identifier in roots:
                mapping.setdefault(identifier, set()).add(variant)
    extra = {}
    for path in args.extra:
        for line in path.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                name, _, value = line.partition("=")
                try:
                    identifier = int(value.strip()) & 0xFFFFFFFF
                except ValueError:
                    continue
                if identifier in roots:
                    extra.setdefault(identifier, set()).add(name.strip())
            else:
                identifier = joaat(line)
                if identifier in roots:
                    extra.setdefault(identifier, set()).add(line)

    before = set(mapping)
    for identifier, labels in extra.items():
        mapping.setdefault(identifier, set()).update(labels)
    print(f"roots: {len(roots)}, named: {len(mapping)}, unmatched: {len(roots) - len(mapping)}")
    print(f"candidate strings: {len(names)}")
    if args.extra:
        print(f"extra files: {len(args.extra)}, additional roots: {len(set(mapping) - before)}")
    for identifier, labels in sorted(mapping.items()):
        print(f"0x{identifier:08x}\t{','.join(sorted(labels))}")
    matched = set(mapping)
    print("unmatched roots:")
    for identifier in roots:
        if identifier not in matched:
            print(f"0x{identifier:08x}")


if __name__ == "__main__":
    main()
