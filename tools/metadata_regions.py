"""Compare the three RPF9 metadata regions across the observed controls."""

import argparse
from collections import Counter, defaultdict
import math
from pathlib import Path
import re
import struct
import subprocess

SCOPES = (
    ("appdata0.rpf", "appdata0", 0, None),
    ("common.rpf", "common", 0, None),
    ("core_licenses_data.rpf", "core root", 0, None),
    ("core_licenses_data.rpf", "core @0x1000", 0x1000, 0x2e50),
    ("script.rpf", "script root", 0, None),
    ("script.rpf", "script @0x1000", 0x1000, 0xc3b90),
    ("script.rpf", "script @0xc4000", 0xc4000, 0x4282b0),
    ("story000_bvh4.rpf", "story000_bvh4", 0, None),
)


def entropy(data):
    if not data:
        return 0.0
    counts = [0] * 256
    for byte in data:
        counts[byte] += 1
    return -sum(
        (count / len(data)) * math.log2(count / len(data))
        for count in counts
        if count
    )


def metrics(cli, path, start, end):
    report = subprocess.check_output(
        [str(cli), "partition", str(path), f"{start:x}", f"{end:x}"],
        text=True,
    )
    result = {}
    for line in report.splitlines():
        if not line:
            break
        key, value = line.split("\t", 1)
        result[key] = value
    return result


def header_word(data, start, offset):
    return struct.unpack_from("<I", data, start + offset)[0]


def scope_rows(archive_dir, cli):
    rows = []
    for name, label, start, end in SCOPES:
        path = archive_dir / name
        data = path.read_bytes()
        end = len(data) if end is None else end
        words = struct.unpack_from("<24I", data, start)
        front_end, front_block, trailer_bytes = words[1], words[2], words[3]
        count = words[9]
        if not (0x60 <= front_block <= front_end):
            raise ValueError(f"{label}: invalid front boundaries")
        if trailer_bytes > end - start:
            raise ValueError(f"{label}: trailer exceeds pack")
        stats = metrics(cli, path, start, end)
        rows.append(
            {
                "label": label,
                "path": path,
                "data": data,
                "start": start,
                "end": end,
                "words": words,
                "count": count,
                "front_a": front_block - 0x60,
                "front_b": front_end - front_block,
                "trailer": trailer_bytes,
                "trailer_bytes": data[end - trailer_bytes : end],
                "streams": int(stats["verified_streams"]),
                "chains": int(stats["candidate_zlib_chains"]),
                "opaque": int(stats["opaque_spans"]),
                "embedded": int(stats["inferred_embedded_packs"]),
                "candidates": int(stats["candidate_entries"]),
            }
        )
    return rows


def print_regions(rows):
    print("regions: Front A = 0x60..+0x08, Front B = +0x08..+0x04, Trailer = end-+0x0c..end")
    print(
        "scope\tN\tstreams\tchains\topaque\tembedded\tcandidates\t"
        "front_a\tfront_b\ttrailer\tfront_a_minus_0x100\tA_per_cand\tB_per_N\tT_per_N"
    )
    for row in rows:
        print(
            f'{row["label"]}\t{row["count"]}\t{row["streams"]}\t{row["chains"]}\t'
            f'{row["opaque"]}\t{row["embedded"]}\t{row["candidates"]}\t'
            f'{row["front_a"]}\t{row["front_b"]}\t{row["trailer"]}\t'
            f'{row["front_a"] - 0x100}\t{row["front_a"] / row["candidates"]:.2f}\t'
            f'{row["front_b"] / row["count"]:.2f}\t'
            f'{row["trailer"] / row["count"]:.2f}'
        )


def print_region_alignment(rows):
    print("\n16-byte alignment of region sizes")
    for row in rows:
        values = (row["front_a"], row["front_b"], row["trailer"])
        print(f'{row["label"]}: {values} -> ' + ", ".join(str(v % 16) for v in values))


def print_header_words(rows):
    print("\nheader words: distinct values across the eight scopes")
    for offset in range(0, 0x60, 4):
        values = {row["words"][offset // 4] for row in rows}
        text = " ".join(f"{value:08x}" for value in sorted(values))
        print(f"+0x{offset:02x}\t{len(values)}\t{text}")


def print_header_varying(rows):
    print("\nper-scope header words that vary")
    print("scope\tN\t+0x10\t+0x14\t+0x18\t+0x1c\t+0x20\t+0x24\t+0x28\t+0x2c\t+0x30")
    for row in rows:
        values = row["words"]
        print(
            f'{row["label"]}\t{row["count"]}\t' +
            "\t".join(f"{values[i]:08x}" for i in (4, 5, 6, 7, 8, 9, 10, 11, 12))
        )


def print_trailer_prefixes(rows):
    print("\ntrailer prefixes")
    for row in rows:
        print(f'{row["label"]}: {row["trailer_bytes"][:32].hex()}')
    for size in (16, 32, 48, 64):
        groups = defaultdict(list)
        for row in rows:
            if len(row["trailer_bytes"]) >= size:
                groups[row["trailer_bytes"][:size]].append(row["label"])
        shared = [labels for labels in groups.values() if len(labels) > 1]
        print(f"first {size:2} bytes shared by: {shared}")


def print_trailer_alignment(rows):
    print("\ntrailer shared prefixes and aligned block repeats")
    for index, first in enumerate(rows):
        for second in rows[index + 1 :]:
            left, right = first["trailer_bytes"], second["trailer_bytes"]
            length = min(len(left), len(right))
            prefix = next(
                (offset for offset in range(length) if left[offset] != right[offset]),
                length,
            )
            if prefix >= 8:
                print(
                    f'  {first["label"]} vs {second["label"]}: '
                    f"shared {prefix} bytes (mod16={prefix % 16})"
                )
    counts = Counter()
    for row in rows:
        trailer = row["trailer_bytes"]
        for offset in range(0, len(trailer) - 15, 16):
            counts[trailer[offset : offset + 16]] += 1
    repeated = {value: count for value, count in counts.items() if count > 1}
    print(
        f"  aligned blocks {sum(counts.values())}, unique {len(counts)}, "
        f"repeated values {len(repeated)}, repeated occurrences {sum(repeated.values())}"
    )
    for value, count in counts.most_common(6):
        if count > 1:
            print(f"    {count} {value.hex()}")


def print_trailer_diffs(rows):
    print("\ntrailer suffix XOR for scopes sharing the first 32 bytes")
    groups = defaultdict(list)
    for row in rows:
        if len(row["trailer_bytes"]) >= 32:
            groups[row["trailer_bytes"][:32]].append(row)
    for group in groups.values():
        if len(group) != 2:
            continue
        first, second = group
        length = min(len(first["trailer_bytes"]), len(second["trailer_bytes"]))
        if length <= 32:
            continue
        diff = bytes(
            left ^ right
            for left, right in zip(
                first["trailer_bytes"][32:length], second["trailer_bytes"][32:length]
            )
        )
        ones = sum((byte >> 7) & 1 for byte in diff)
        print(
            f'{first["label"]} ^ {second["label"]}: {len(diff)} bytes, '
            f"bit7 ones {ones} ({ones / len(diff):.1%}), "
            f"max {max(diff)}, min {min(diff)}"
        )


def print_front_a_split(rows):
    print("\nFront A split at the 0x100-byte boundary after +0x60")
    print("scope\tA_bytes\tsig_span\tsig_entropy\trest_bytes\trest_entropy")
    for row in rows:
        data, start, block = row["data"], row["start"], row["words"][2]
        signature = data[start + 0x60 : start + 0x160]
        rest = data[start + 0x160 : start + block]
        print(
            f'{row["label"]}\t{row["front_a"]}\t{len(signature)}\t'
            f"{entropy(signature):.4f}\t{len(rest)}\t{entropy(rest):.4f}"
        )


def print_directory_inventory(archive_dir):
    xml_dir = archive_dir / "output" / "common.rpf"
    if not xml_dir.is_dir():
        print("\nXML output directory not found; skipping directory inventory")
        return
    text = "\n".join(path.read_text(errors="ignore") for path in xml_dir.glob("*.xml"))
    print("\ndirectory prefixes referenced by the recovered common.rpf XML")
    combined = set()
    for scheme in ("common:", "$(root)"):
        paths = set(re.findall(re.escape(scheme) + r'/[^"<>&\s]+', text))
        nodes = set()
        for path in paths:
            parts = path.split("/")
            for index in range(1, len(parts)):
                nodes.add("/".join(parts[:index]))
        nodes.discard(scheme)
        combined |= nodes
        print(f"{scheme}: {len(paths)} paths, {len(nodes)} directory prefixes")
    print(f"combined directory prefixes (mount labels excluded): {len(combined)}")
    for node in sorted(combined):
        print(f"  {node}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive_dir", type=Path, help="directory containing the local samples")
    parser.add_argument(
        "--cli", type=Path, default=Path("target/debug/rage-tools-vi")
    )
    args = parser.parse_args()
    rows = scope_rows(args.archive_dir, args.cli)
    print_regions(rows)
    print_region_alignment(rows)
    print_header_words(rows)
    print_header_varying(rows)
    print_trailer_prefixes(rows)
    print_trailer_alignment(rows)
    print_trailer_diffs(rows)
    print_front_a_split(rows)
    print_directory_inventory(args.archive_dir)


if __name__ == "__main__":
    main()
