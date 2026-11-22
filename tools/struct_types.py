"""Partition the script.rpf object tree by record size and tagged-pointer layout."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
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


def record_layout(data, offset, end):
    pointers = []
    for position in range(offset, end - 7, 8):
        _, tag = struct.unpack_from("<II", data, position)
        if tag == 0x71717171:
            pointers.append(position - offset)
    return tuple(pointers)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--no-names", action="store_true")
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    count = struct.unpack_from("<I", data, 0x14)[0]
    offsets = struct.unpack_from(f"<{count}Q", data, 0x28)
    names = set() if args.no_names else candidates(Path("."), True)
    lookup = {}
    for name in names:
        for variant in {name, name.lower()}:
            lookup.setdefault(joaat(variant), set()).add(variant)

    groups = defaultdict(list)
    for index, offset in enumerate(offsets):
        end = offsets[index + 1] if index + 1 < count else len(data)
        groups[(end - offset, record_layout(data, offset, end))].append(index)

    print(f"records: {count}, struct groups: {len(groups)}")
    print(f"size groups: {len({size for size, _ in groups})}")
    print("count\tsize\tpointer_offsets\tname_at_0\tname_at_0x10\texample_record\texample_offset")
    for (size, pointers), indices in sorted(groups.items(), key=lambda item: -len(item[1]))[: args.limit]:
        example = indices[0]
        offset = offsets[example]
        if lookup:
            names0 = Counter(
                name
                for index in indices
                for value in [struct.unpack_from("<I", data, offsets[index])[0]]
                for name in lookup.get(value, ())
            )
            names10 = Counter(
                name
                for index in indices
                if size >= 20
                for value in [struct.unpack_from("<I", data, offsets[index] + 0x10)[0]]
                for name in lookup.get(value, ())
            )
            label0 = ",".join(name for name, _ in names0.most_common(3))
            label10 = ",".join(name for name, _ in names10.most_common(3))
        else:
            label0 = label10 = ""
        print(
            f"{len(indices)}\t{size}\t{pointers}\t{label0}\t{label10}\t"
            f"{example}\t0x{offset:x}"
        )

    print("\nsize-only counts")
    sizes = Counter()
    for (size, _), indices in groups.items():
        sizes[size] += len(indices)
    for size, total in sizes.most_common(args.limit):
        masks = {pointers for (group_size, pointers) in groups if group_size == size}
        print(f"  size {size:5}: {total:5} records, {len(masks)} pointer layouts")

    print("\n32-byte layouts")
    for (size, pointers), indices in sorted(groups.items(), key=lambda item: -len(item[1])):
        if size != 32:
            continue
        print(f"  {len(indices):4} records, pointers={pointers}")
        example = indices[0]
        offset = offsets[example]
        print(f"    example {example} at 0x{offset:x}: {data[offset:offset+32].hex()}")


if __name__ == "__main__":
    main()
