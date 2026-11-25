#!/usr/bin/env python3
"""Inventory vehicle-like roots and their mover-curve coverage."""
import argparse
import csv
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
            [str(cli), "extract-zlib", str(archive), f"{OBJECT_START:x}", f"{OBJECT_END:x}", str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        return path.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--curves", type=Path, default=Path("handoff/script-vehicle-curves.tsv"))
    parser.add_argument("--tsv", type=Path, default=Path("handoff/script-vehicles.tsv"))
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    count = struct.unpack_from("<I", data, 0x14)[0]
    offsets = struct.unpack_from(f"<{count}Q", data, 0x28)
    by_address = {offset + 8: index for index, offset in enumerate(offsets)}

    def end(index):
        return offsets[index + 1] if index + 1 < count else len(data)

    targets = set()
    for position in range(0, len(data) - 7, 8):
        address, tag = struct.unpack_from("<II", data, position)
        if tag == 0x71717171:
            targets.add(address)

    lookup = {}
    for name in candidates(Path("."), True):
        for variant in {name, name.lower()}:
            lookup.setdefault(joaat(variant), variant)

    curves = defaultdict(list)
    if args.curves.is_file():
        for row in csv.DictReader(args.curves.open(newline="", encoding="utf-8"), delimiter="\t"):
            curves[row["root_id"]].append(row)

    roots = []
    for index, offset in enumerate(offsets):
        if offset + 8 in targets:
            continue
        flags = struct.unpack_from("<I", data, offset + 4)[0]
        if flags >> 16 != 0xFFFF:
            continue
        root_id = struct.unpack_from("<I", data, offset)[0]
        key = f"0x{root_id:08x}"
        entries = curves.get(key, [])
        roots.append((index, key, lookup.get(root_id, ""), flags, entries))

    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["root_record", "root_id", "root_name", "flags", "curve_count", "channels"])
        for index, root_id, name, flags, entries in roots:
            channels = sorted({entry["key_hash"] for entry in entries})
            writer.writerow([
                index, root_id, name, f"0x{flags:08x}", len(entries), ",".join(channels)
            ])

    named = sum(1 for root in roots if root[2])
    with_curves = sum(1 for root in roots if root[4])
    print(f"vehicle-like roots: {len(roots)}; named: {named}; with curves: {with_curves}")
    print("root_id\tname\tcurves\tchannels")
    for index, root_id, name, flags, entries in roots[:20]:
        print(f"{root_id}\t{name or '-'}\t{len(entries)}\t{len({e['key_hash'] for e in entries})}")


if __name__ == "__main__":
    main()
