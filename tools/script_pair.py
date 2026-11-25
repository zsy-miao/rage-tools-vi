"""Inspect the two entries in the script.rpf pack at 0x1000."""

import argparse
import math
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from root_names import candidates, joaat  # noqa: E402

OBJECT_START, OBJECT_END = 0x53000, 0xC3B45
BLOB_START, BLOB_END = 0x2010, 0x52FE0


def entropy(data):
    counts = [0] * 256
    for byte in data:
        counts[byte] += 1
    return -sum(
        (count / len(data)) * math.log2(count / len(data))
        for count in counts
        if count
    )


def extract(cli, archive, mode, start, end, path):
    subprocess.run(
        [
            str(cli),
            mode,
            str(archive),
            f"{start:x}",
            f"{end:x}",
            str(path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    return path.read_bytes()


def parse_object(data):
    count = struct.unpack_from("<I", data, 0x14)[0]
    offsets = struct.unpack_from(f"<{count}Q", data, 0x28)
    targets = set()
    for position in range(0, len(data) - 7, 8):
        address, tag = struct.unpack_from("<II", data, position)
        if tag == 0x71717171:
            targets.add(address)
    roots = []
    for index, offset in enumerate(offsets):
        identifier = struct.unpack_from("<I", data, offset)[0]
        if identifier and offset + 8 not in targets:
            roots.append((index, offset, identifier))
    return count, offsets, targets, roots


def search(blob, values, width):
    hits = []
    pattern = "<Q" if width == 8 else "<I"
    for value in values:
        packed = struct.pack(pattern, value if width == 8 else value & 0xFFFFFFFF)
        position = blob.find(packed)
        if position >= 0:
            hits.append((value, position))
    return hits


def periodic_runs(data, minimum_repeats=5):
    runs = []
    for period in range(2, 17):
        start = 0
        while start + period * minimum_repeats <= len(data):
            end = start + period
            while end + period <= len(data) and data[end : end + period] == data[end - period : end]:
                end += period
            repeats = (end - start) // period
            if repeats >= minimum_repeats:
                runs.append((period, start, repeats, end))
                start = end
            else:
                start += 1
    return runs


def printable_runs(data, minimum=10):
    return re.findall(rb"[\x20-\x7e]{%d,}" % minimum, data)


def try_zlib(data):
    hits = []
    for offset in range(0, len(data) - 1):
        if data[offset] == 0x78 and data[offset + 1] in (0x01, 0x5E, 0x9C, 0xDA):
            try:
                decoder = zlib.decompressobj()
                decoded = decoder.decompress(data[offset:])
            except Exception:
                continue
            if decoder.eof and len(decoded) >= 1024:
                hits.append((offset, len(decoded)))
    return hits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--no-names", action="store_true")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as directory:
        object_path = Path(directory) / "object.bin"
        blob_path = Path(directory) / "blob.bin"
        obj = extract(args.cli, args.archive, "extract-zlib", OBJECT_START, OBJECT_END, object_path)
        blob = extract(args.cli, args.archive, "extract-raw", BLOB_START, BLOB_END, blob_path)

    print(f"object: {len(obj)} bytes, entropy {entropy(obj):.4f}")
    print(f"blob:   {len(blob)} bytes, entropy {entropy(blob):.4f}, mod16 {len(blob) % 16}")
    count, offsets, targets, roots = parse_object(obj)
    print(
        f"object records: {count}, offsets {offsets[0]:#x}..{offsets[-1]:#x}, "
        f"tagged targets {len(targets)}, roots {len(roots)}"
    )

    print("\nindex searches in the blob")
    for width in (8, 4):
        offset_hits = search(blob, offsets, width)
        target_hits = search(blob, sorted(targets), width)
        print(
            f"  {width}-byte offsets: {len(offset_hits)}/{len(offsets)}; "
            f"targets: {len(target_hits)}/{len(targets)}"
        )
        if offset_hits[:3]:
            print(f"    offset hits {offset_hits[:3]}")
        if target_hits[:3]:
            print(f"    target hits {target_hits[:3]}")

    for endian in ("<", ">"):
        hits = [
            (identifier, blob.find(struct.pack(endian + "I", identifier)))
            for _, _, identifier in roots
        ]
        hits = [hit for hit in hits if hit[1] >= 0]
        print(f"  {endian}-endian root IDs in blob: {len(hits)}/{len(roots)}")

    for width, pattern in ((4, "<I"), (8, "<Q")):
        packed = struct.pack(pattern, len(blob))
        print(
            f"  blob size {len(blob)} as {width}-byte LE: "
            f"blob at {blob.find(packed)}, object at {obj.find(packed)}"
        )

    if not args.no_names:
        names = candidates(Path("."), True)
        lookup = {}
        for name in names:
            for variant in {name, name.lower()}:
                lookup.setdefault(joaat(variant), set()).add(variant)
        name_hits = []
        for position in range(0, len(blob) - 3, 4):
            value = struct.unpack_from("<I", blob, position)[0]
            if value in lookup:
                name_hits.append((position, value, sorted(lookup[value])))
        expected = len(blob) // 4 * len(lookup) / 2**32
        print(f"\nblob JOAAT hits: {len(name_hits)} (expected {expected:.2f})")
        for position, value, labels in name_hits[:10]:
            print(f"  0x{position:x} 0x{value:08x} {','.join(labels)}")

    print("\nperiodic runs in the blob")
    runs = periodic_runs(blob)
    for period, start, repeats, end in runs:
        print(f"  period {period:2}: {start:#x}..{end:#x}, {repeats} repeats")

    seven = [run for run in runs if run[0] == 7 and run[2] >= 20]
    for _, start, _, end in seven:
        key = blob[start : start + 7]
        phase = (-start) % 7
        decoded = bytes(byte ^ key[(index + phase) % 7] for index, byte in enumerate(blob))
        zero_run = decoded[start:end]
        print(
            f"\n7-byte unit at {start:#x}: {key.hex()}, phase {phase}; "
            f"run XORed with its own unit decodes to {zero_run.count(0)}/{len(zero_run)} zeros"
        )
        print(
            f"  decoded blob: zeros {decoded.count(0)}, printable "
            f"{sum(1 for byte in decoded if 32 <= byte < 127)}, "
            f"longest printable run {max((len(run) for run in printable_runs(decoded)), default=0)}"
        )
        print(f"  zlib streams in decoded blob: {try_zlib(decoded)[:5]}")
        print(f"  decoded first 32 bytes: {decoded[:32].hex()}")
        print(f"  decoded run surroundings: {decoded[start - 16 : end + 32].hex()}")


if __name__ == "__main__":
    main()
