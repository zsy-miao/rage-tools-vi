"""Map JOAAT name fields across the script.rpf object tree."""

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from pathlib import Path
import re
import struct
import subprocess
import tempfile

OBJECT_START, OBJECT_END = 0x53000, 0xC3B45
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


def parse_tree(data):
    count = struct.unpack_from("<I", data, 0x14)[0]
    offsets = struct.unpack_from(f"<{count}Q", data, 0x28)
    by_address = {offset + 8: index for index, offset in enumerate(offsets)}
    parent = [None] * count
    children = [[] for _ in offsets]
    for position in range(0, len(data) - 7, 8):
        address, tag = struct.unpack_from("<II", data, position)
        if tag != 0x71717171 or address not in by_address:
            continue
        source = bisect_right(offsets, position) - 1
        target = by_address[address]
        if 0 <= source < count:
            children[source].append(target)
            parent[target] = source
    roots = [index for index, value in enumerate(parent) if value is None]
    root_of = [None] * count
    for root in roots:
        stack = [root]
        while stack:
            index = stack.pop()
            root_of[index] = root
            stack.extend(children[index])
    return count, offsets, roots, children, root_of


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--archive-dir", type=Path, default=Path("."))
    parser.add_argument("--no-wordlist", action="store_true")
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    count, offsets, roots, children, root_of = parse_tree(data)
    names = candidates(args.archive_dir, not args.no_wordlist)
    lookup = {}
    for name in names:
        for variant in {name, name.lower()}:
            lookup.setdefault(joaat(variant), set()).add(variant)

    hits = []
    for position in range(0, len(data) - 3, 4):
        value = struct.unpack_from("<I", data, position)[0]
        if value not in lookup:
            continue
        record = bisect_right(offsets, position) - 1
        if record < 0:
            continue
        hits.append(
            {
                "position": position,
                "record": record,
                "field": position - offsets[record],
                "names": sorted(lookup[value]),
            }
        )

    print(f"records: {count}, roots: {len(roots)}")
    print(f"name hits: {len(hits)}, unique names: {len({name for hit in hits for name in hit['names']})}")
    print(f"expected random hits: {len(data) // 4 * len(lookup) / 2**32:.2f}")
    print(f"field offsets: {Counter(hit['field'] for hit in hits).most_common(12)}")
    print(f"top names: {Counter(name for hit in hits for name in hit['names']).most_common(20)}")

    by_root = defaultdict(set)
    root_names = {}
    for hit in hits:
        root = root_of[hit["record"]]
        if root is None:
            continue
        for name in hit["names"]:
            if hit["field"] == 0:
                root_names.setdefault(root, name)
            else:
                by_root[root].add(name)
    print("\nexample named roots and child names")
    shown = 0
    for root in roots:
        if root not in root_names:
            continue
        child_names = sorted(by_root.get(root, ()))
        print(f"  {root_names[root]:20} children={child_names[:12]}")
        shown += 1
        if shown >= 20:
            break

    print("\nname hits by record")
    for hit in hits[:40]:
        root = root_of[hit["record"]]
        label = root_names.get(root, "?")
        print(
            f"  rec {hit['record']:5} field +0x{hit['field']:03x} "
            f"root {label:16} {','.join(hit['names'])}"
        )


if __name__ == "__main__":
    main()
