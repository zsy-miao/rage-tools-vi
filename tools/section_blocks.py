"""Test 16-byte block repetition in the decoded PSIN sections of script.rpf."""

import argparse
from collections import Counter, defaultdict
import csv
from pathlib import Path
import struct
import subprocess
import zlib

SECTION_HEADERS = {
    "PSIN": 8,
    "LSCH": 16,
    "LENM": 8,
    "LSNS": 12,
    "LGID": None,
    "LRSC": 16,
    "CHKS": None,
}


def read_records(cli, path, start, end):
    data = path.read_bytes()
    report = subprocess.check_output(
        [str(cli), "map", str(path), f"{start:x}", f"{end:x}"], text=True
    )
    rows = list(csv.DictReader(report.splitlines(), delimiter="\t"))
    chains = defaultdict(list)
    cursor = start
    for row in rows:
        row_start = int(row["start"], 16)
        row_end = int(row["end"], 16)
        if row_start != cursor or row_end <= row_start:
            raise ValueError("range map does not partition the pack")
        cursor = row_end
        if row["kind"] != "zlib":
            continue
        decoder = zlib.decompressobj()
        decoded = decoder.decompress(data[row_start:row_end])
        if not decoder.eof or decoder.unused_data:
            raise ValueError(f"invalid zlib stream at {row_start:#x}")
        if len(decoded) != int(row["decoded_bytes"]):
            raise ValueError(f"decoded size differs at {row_start:#x}")
        chains[int(row["chain_start"], 16)].append(decoded)
    if cursor != end:
        raise ValueError("range map ends early")

    records = []
    for chain in sorted(chains):
        data = b"".join(chains[chain])
        offset = 0
        sections = {}
        while offset < len(data):
            tag = data[offset : offset + 4].decode("ascii")
            size = struct.unpack_from(">I", data, offset + 4)[0]
            if not tag.isupper() or size < 8 or offset + size > len(data):
                raise ValueError(f"invalid section at {offset:#x}")
            sections[tag] = data[offset + 8 : offset + size]
            offset += size
        if offset != len(data):
            raise ValueError("record does not end at a section boundary")
        records.append(sections)
    return records


def block_stats(blocks):
    """blocks are (record, index, value, predecessor-or-None)."""
    values = Counter(block[2] for block in blocks)
    repeated = {value: count for value, count in values.items() if count > 1}
    same_pred = 0
    diff_pred = 0
    first_repeats = 0
    for value, count in repeated.items():
        occurrences = [block for block in blocks if block[2] == value]
        predecessors = Counter(block[3] for block in occurrences)
        same_pred += sum(n for n in predecessors.values() if n > 1)
        diff_pred += sum(n for n in predecessors.values() if n == 1)
        first_repeats += sum(1 for block in occurrences if block[1] == 0)
    return {
        "blocks": len(blocks),
        "unique": len(values),
        "repeated_values": len(repeated),
        "repeated_occurrences": sum(repeated.values()),
        "same_pred": same_pred,
        "diff_pred": diff_pred,
        "first_repeats": first_repeats,
    }


def collect_blocks(records, tag, header):
    blocks = []
    lengths = []
    for record_index, sections in enumerate(records):
        body = sections[tag]
        lengths.append(len(body))
        if header is None:
            continue
        payload = body[header:]
        if len(payload) % 16:
            raise ValueError(f"{tag} payload is not block-aligned")
        for index in range(0, len(payload), 16):
            blocks.append(
                (
                    record_index,
                    index // 16,
                    payload[index : index + 16],
                    payload[index - 16 : index] if index else None,
                )
            )
    return blocks, lengths


def print_unique_blocks(blocks, limit):
    counts = Counter(block[2] for block in blocks)
    for value, count in counts.most_common(limit):
        print(f"  {count:6} {value.hex()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--start", default="c4000")
    parser.add_argument("--end", default="4282b0")
    args = parser.parse_args()
    start = int(args.start, 16)
    end = int(args.end, 16)
    records = read_records(args.cli, args.archive, start, end)
    print(f"records: {len(records)}")

    print("\nsection body lengths and selected header")
    for tag in SECTION_HEADERS:
        lengths = [len(sections.get(tag, b"")) for sections in records]
        print(
            f"{tag}: n={len(lengths)} min={min(lengths)} max={max(lengths)} "
            f"mod16={dict(Counter(length % 16 for length in lengths))} "
            f"header={SECTION_HEADERS[tag]}"
        )

    print("\nLSNS plaintext header")
    bad = 0
    for sections in records:
        body = sections["LSNS"]
        first, second, declared = struct.unpack_from("<III", body, 0)
        payload = body[12:]
        if (first, second) != (1, 257) or declared != len(payload) or declared % 16:
            bad += 1
    print(
        f"records with (1, 257, block_bytes) header and exact block padding: "
        f"{len(records) - bad}/{len(records)}"
    )

    print(
        "\nblock repetition; same_pred counts occurrences of a repeated block "
        "whose predecessor is also repeated"
    )
    print(
        "section\theader\tblocks\tunique\trepeated_values\trepeated_occ\t"
        "same_pred\tdiff_pred\tfirst_repeats"
    )
    for tag, header in SECTION_HEADERS.items():
        if header is None:
            continue
        blocks, _ = collect_blocks(records, tag, header)
        stats = block_stats(blocks)
        print(
            f"{tag}\t{header}\t{stats['blocks']}\t{stats['unique']}\t"
            f"{stats['repeated_values']}\t{stats['repeated_occurrences']}\t"
            f"{stats['same_pred']}\t{stats['diff_pred']}\t{stats['first_repeats']}"
        )

    print("\nLENM unique blocks")
    blocks, _ = collect_blocks(records, "LENM", SECTION_HEADERS["LENM"])
    print_unique_blocks(blocks, 16)
    print("\nLRSC unique blocks")
    blocks, _ = collect_blocks(records, "LRSC", SECTION_HEADERS["LRSC"])
    print_unique_blocks(blocks, 16)
    print("\nLSCH unique blocks")
    blocks, _ = collect_blocks(records, "LSCH", SECTION_HEADERS["LSCH"])
    print_unique_blocks(blocks, 40)
    print("\nPSIN most frequent blocks")
    blocks, _ = collect_blocks(records, "PSIN", SECTION_HEADERS["PSIN"])
    print_unique_blocks(blocks, 8)

    print("\nLSNS repeated blocks: value, count, and first positions")
    blocks, _ = collect_blocks(records, "LSNS", SECTION_HEADERS["LSNS"])
    counts = Counter(block[2] for block in blocks)
    for value, count in counts.most_common(6):
        positions = [(block[0], block[1]) for block in blocks if block[2] == value]
        predecessors = {block[3] for block in blocks if block[2] == value}
        print(f"  {count:4} {value.hex()} positions={positions[:6]} predecessors={len(predecessors)}")


if __name__ == "__main__":
    main()
