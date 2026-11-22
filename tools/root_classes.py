"""Classify object-tree roots by their child part/bone signatures."""

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
KEYWORDS = {
    "car": {"boot", "bonnet", "chassis", "door", "wheel", "bumper", "fender", "suspension", "brake", "engine", "transmission", "exhaust", "mirror", "plate", "livery"},
    "bike": {"handlebars", "forks", "fork", "frame", "seat", "tank"},
    "helicopter": {"rotor", "rotor_main", "rotor_tail", "blade", "tail", "skid"},
    "aircraft": {"wing", "aileron", "rudder", "elevator", "propeller", "prop", "flap", "fuselage"},
    "boat": {"hull", "rudder", "propeller", "mast", "sail"},
    "ped_or_skeleton": {"skel_spine1", "skel_spine2", "skel_spine3", "skel_neck1", "skel_neck2", "skel_l_calf", "skel_r_calf", "skel_l_foot", "skel_r_foot"},
    "trailer": {"trailer", "hitch", "axle"},
    "weapon": {"weapon", "barrel", "magazine", "stock", "scope"},
}


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
    parser.add_argument("--limit", type=int, default=30)
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

    def children(index):
        result = []
        for position in range(offsets[index], end(index) - 7, 8):
            address, tag = struct.unpack_from("<II", data, position)
            if tag == 0x71717171 and address in by_address:
                result.append(by_address[address])
        return result

    parent = [None] * count
    for source in range(count):
        for target in children(source):
            parent[target] = source
    roots = [index for index, value in enumerate(parent) if value is None]

    def descendants(index, seen=None):
        if seen is None:
            seen = set()
        if index in seen:
            return set()
        seen.add(index)
        result = set()
        for target in children(index):
            name = name_at(target, 0) or name_at(target, 0x10)
            if name:
                result.add(name)
            result |= descendants(target, seen)
        return result

    def classify(names):
        for label, words in KEYWORDS.items():
            if names & words:
                return label
        return None

    named = {identifier: labels for identifier, labels in lookup.items() if identifier in roots}
    classes = Counter()
    shapes = Counter()
    unnamed = []
    for root in roots:
        root_name = name_at(root, 0)
        child_names = descendants(root)
        label = classify(child_names) or "unknown"
        flags = struct.unpack_from("<I", data, offsets[root] + 4)[0]
        pointers = len(children(root))
        if flags == 0xFFFF0000 and pointers == 1:
            shape = "vehicle_like"
        elif flags == 0 and pointers == 1:
            shape = "flags_0"
        else:
            shape = f"flags_{flags:x}_ptrs_{pointers}"
        classes[f"{shape}/{label}"] += 1
        shapes[(shape, "named" if root_name else "unnamed")] += 1
        if root_name is None:
            unnamed.append((root, shape, label, child_names))

    print("root shapes")
    for (shape, status), total in sorted(shapes.items()):
        print(f"  {status:8} {shape}: {total}")

    print("\nheader +0x04 split")
    header_classes = Counter()
    other_high = []
    for root in roots:
        flags = struct.unpack_from("<I", data, offsets[root] + 4)[0]
        high = flags >> 16
        named = name_at(root, 0) is not None
        header_classes[(high, "named" if named else "unnamed")] += 1
        if high not in (0, 0xFFFF):
            targets = children(root)
            child_type = (
                struct.unpack_from("<I", data, offsets[targets[0]] + 8)[0]
                if targets
                else None
            )
            other_high.append(
                (
                    root,
                    struct.unpack_from("<I", data, offsets[root])[0],
                    flags,
                    child_type,
                    len(targets),
                )
            )
    for (high, status), total in sorted(header_classes.items()):
        print(f"  high={high:#06x} {status}: {total}")
    print("  other-high roots:")
    for root, identifier, flags, child_type, pointers in other_high:
        print(
            f"    0x{identifier:08x} flags=0x{flags:08x} "
            f"bytes={struct.pack('<I', flags).hex()} "
            f"child_type={hex(child_type) if child_type else None} pointers={pointers}"
        )

    print("\nroot classes by shape and child signature")
    for label, total in classes.most_common():
        print(f"  {label}: {total}")

    print("\nunnamed roots by signature")
    for root, shape, label, names in unnamed[: args.limit]:
        print(
            f"  0x{struct.unpack_from('<I', data, offsets[root])[0]:08x} "
            f"{shape}/{label} children={sorted(names)[:10]}"
        )


if __name__ == "__main__":
    main()
