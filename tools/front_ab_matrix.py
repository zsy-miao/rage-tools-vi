"""Compare Front A/B equality across languages and tabulate B-size modes."""

import argparse
import csv
from collections import defaultdict
from pathlib import Path
import struct


def align16(value):
    return (value + 15) // 16 * 16


def parse_pack_starts(path):
    packs = {}
    lines = Path(path).read_text().splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("pack_start\tfirst_psin_valid"):
            continue
        header = line.split("\t")
        for row_line in lines[index + 1 :]:
            if not row_line.strip():
                break
            values = row_line.split("\t")
            if len(values) != len(header):
                continue
            row = dict(zip(header, values))
            if row.get("language"):
                packs[row["language"]] = int(row["pack_start"], 16)
        break
    return packs


def read_fronts(data, base):
    data.seek(base)
    header = data.read(0x60)
    front_end = struct.unpack_from("<I", header, 4)[0]
    block = struct.unpack_from("<I", header, 8)[0]
    data.seek(base + 0x60)
    front_a = data.read(block - 0x60)
    data.seek(base + block)
    front_b = data.read(front_end - block)
    return front_a, front_b


def common_prefix(left, right):
    length = min(len(left), len(right))
    for index in range(length):
        if left[index] != right[index]:
            return index
    return length


def common_suffix(left, right):
    length = min(len(left), len(right))
    for offset in range(1, length + 1):
        if left[-offset] != right[-offset]:
            return offset - 1
    return length


def equal_blocks(left, right, shift):
    blocks = 0
    total = 0
    for index in range(0, min(len(left), len(right)) // 16):
        other = index + shift
        if other < 0 or other >= len(right) // 16:
            continue
        total += 1
        if left[index * 16 : index * 16 + 16] == right[other * 16 : other * 16 + 16]:
            blocks += 1
    return blocks, total


def matrix(left, right):
    return {
        "prefix": common_prefix(left, right),
        "suffix": common_suffix(left, right),
        "equal": sum(1 for a, b in zip(left, right) if a == b),
        "length": min(len(left), len(right)),
        "same_blocks": equal_blocks(left, right, 0),
        "shift_blocks": sum(equal_blocks(left, right, shift)[0] for shift in range(-2, 3)),
        "shift_total": sum(equal_blocks(left, right, shift)[1] for shift in range(-2, 3)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data.rpf"))
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("output/data.rpf/inventory.txt"),
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=["american", "brazilian", "german"],
    )
    args = parser.parse_args()

    packs = parse_pack_starts(args.inventory)
    data = args.data.open("rb")
    fronts = {}
    print("language\tA_bytes\tB_bytes")
    for language in args.languages:
        front_a, front_b = read_fronts(data, packs[language])
        fronts[language] = (front_a, front_b)
        print(f"{language}\t{len(front_a)}\t{len(front_b)}")

    print("\npair\tregion\tprefix\tsuffix\tequal/total\tsame16\tshift16")
    for index, left_name in enumerate(args.languages):
        for right_name in args.languages[index + 1 :]:
            for region in (0, 1):
                left = fronts[left_name][region]
                right = fronts[right_name][region]
                result = matrix(left, right)
                same_blocks, same_total = result["same_blocks"]
                print(
                    f"{left_name} vs {right_name}\t{'A' if region == 0 else 'B'}\t"
                    f"{result['prefix']}\t{result['suffix']}\t"
                    f"{result['equal']}/{result['length']}\t"
                    f"{same_blocks}/{same_total}\t"
                    f"{result['shift_blocks']}/{result['shift_total']}"
                )

    print("\nFront B size by mode")
    scopes = [
        ("story", "story000_bvh4.rpf", 0),
        ("core_root", "core_licenses_data.rpf", 0),
        ("core_emb", "core_licenses_data.rpf", 0x1000),
        ("appdata0", "appdata0.rpf", 0),
        ("script_root", "script.rpf", 0),
        ("script_small", "script.rpf", 0x1000),
        ("script_large", "script.rpf", 0xC4000),
        ("data_root", "data.rpf", 0),
        ("localization", "data.rpf", packs["american"]),
    ]
    print("scope\tN\tB_bytes\talign16(10N)\tminus10\talign16(12N)\tminus12\t+0x20\t+0x2c")
    for label, filename, base in scopes:
        try:
            with open(filename, "rb") as handle:
                handle.seek(base)
                header = handle.read(0x60)
        except FileNotFoundError:
            continue
        if len(header) < 0x60 or header[:4] != b"9FPR":
            continue
        front_end = struct.unpack_from("<I", header, 4)[0]
        block = struct.unpack_from("<I", header, 8)[0]
        count = struct.unpack_from("<I", header, 0x24)[0]
        size_b = front_end - block
        rounded10 = align16(10 * count)
        rounded12 = align16(12 * count)
        print(
            f"{label}\t{count}\t{size_b}\t{rounded10}\t{size_b - rounded10}\t"
            f"{rounded12}\t{size_b - rounded12}\t"
            f"0x{struct.unpack_from('<I', header, 0x20)[0]:08x}\t"
            f"0x{struct.unpack_from('<I', header, 0x2C)[0]:08x}"
        )
    data.close()


if __name__ == "__main__":
    main()
