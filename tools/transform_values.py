"""Follow tagged pointers from named tree parts to their float value leaves."""

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from root_names import candidates, joaat  # noqa: E402

OBJECT_START, OBJECT_END = 0x53000, 0xC3B45
ROTATION_HASH = 0xFC86DDE2


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


def build_lookup():
    lookup = {}
    for name in candidates(Path("."), True):
        for variant in {name, name.lower()}:
            lookup.setdefault(joaat(variant), set()).add(variant)
    return lookup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--hash", type=lambda value: int(value, 0), default=ROTATION_HASH)
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    count = struct.unpack_from("<I", data, 0x14)[0]
    offsets = struct.unpack_from(f"<{count}Q", data, 0x28)
    by_address = {offset + 8: index for index, offset in enumerate(offsets)}
    lookup = build_lookup()

    def record_end(index):
        return offsets[index + 1] if index + 1 < count else len(data)

    def pointers(index):
        offset = offsets[index]
        end = record_end(index)
        result = []
        for position in range(offset, end - 7, 8):
            address, tag = struct.unpack_from("<II", data, position)
            if tag == 0x71717171 and address in by_address:
                result.append(by_address[address])
        return result

    def name_at(index, field):
        if offsets[index] + field + 4 > record_end(index):
            return None
        value = struct.unpack_from("<I", data, offsets[index] + field)[0]
        labels = lookup.get(value)
        return sorted(labels)[0] if labels else None

    def leaves(index, seen=None):
        if seen is None:
            seen = set()
        if index in seen:
            return []
        seen.add(index)
        offset = offsets[index]
        end = record_end(index)
        children = pointers(index)
        if not children and end - offset >= 20:
            value = struct.unpack_from("<f", data, offset + 0x10)[0]
            identifier = struct.unpack_from("<I", data, offset + 0x08)[0]
            return [(index, identifier, value)]
        result = []
        for child in children:
            result.extend(leaves(child, seen))
        return result

    named_parts = defaultdict(Counter)
    named_roots = Counter()
    examples = {}
    for index in range(count):
        for field, target in ((0, named_roots), (0x10, None)):
            name = name_at(index, field)
            if not name:
                continue
            values = leaves(index)
            for leaf_index, identifier, value in values:
                if identifier != args.hash:
                    continue
                if not math.isfinite(value) or abs(value) > 1_000_000:
                    continue
                rounded = round(value, 5)
                if field == 0x10:
                    named_parts[name][rounded] += 1
                else:
                    target[name] += 1
                examples.setdefault((name, identifier, rounded), (index, leaf_index))

    print(f"rotation hash: 0x{args.hash:08x}")
    print("part\tfloat\tcount\texample_record\texample_leaf")
    shown = 0
    for name, values in sorted(named_parts.items()):
        for value, total in values.most_common(6):
            example, leaf = examples[(name, args.hash, value)]
            print(f"{name}\t{value:.5f}\t{total}\t{example}\t{leaf}")
            shown += 1
            if shown >= args.limit:
                break
        if shown >= args.limit:
            break

    print("\nrotation float distribution")
    distribution = Counter()
    for values in named_parts.values():
        distribution.update(values)
    for value, total in distribution.most_common(30):
        print(f"  {value:.5f}\t{total}")


if __name__ == "__main__":
    main()
