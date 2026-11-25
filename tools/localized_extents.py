"""Compare localization pack extents and Front A/B across languages."""

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
import struct


def parse_driscoll(path):
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
            language = row.get("language")
            if language:
                packs[language] = int(row["pack_start"], 16)
        break
    return packs


def read_groups(path):
    groups = defaultdict(list)
    for row in csv.DictReader(open(path), delimiter="\t"):
        groups[row["language"]].append(row)
    for rows in groups.values():
        rows.sort(key=lambda row: int(row["stored_start"], 16))
    return groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data.rpf"))
    parser.add_argument(
        "--groups",
        type=Path,
        default=Path("output/data.rpf/localized/groups.tsv"),
    )
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("output/data.rpf/inventory.txt"),
    )
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--search", action="store_true")
    args = parser.parse_args()

    packs = parse_driscoll(args.inventory)
    groups = read_groups(args.groups)
    languages = list(packs)
    data = args.data.open("rb")

    table = {}
    print("pack\tN\tfront_a\tfront_b\ttrailer\tfirst_payload_rel")
    for language in languages:
        base = packs[language]
        data.seek(base)
        header = data.read(0x60)
        front_end = struct.unpack_from("<I", header, 4)[0]
        block = struct.unpack_from("<I", header, 8)[0]
        trailer = struct.unpack_from("<I", header, 12)[0]
        count = struct.unpack_from("<I", header, 0x24)[0]
        first = int(groups[language][0]["stored_start"], 16) - base
        print(
            f"{language}\t{count}\t{block - 0x60}\t{front_end - block}\t"
            f"{trailer}\t0x{first:x}"
        )
        data.seek(base + 0x60)
        front_a = data.read(block - 0x60)
        data.seek(base + block)
        front_b = data.read(front_end - block)
        records = groups[language]
        rows = []
        for index, row in enumerate(records):
            start = int(row["stored_start"], 16) - base
            end = int(row["stored_end"], 16) - base
            following = (
                int(records[index + 1]["stored_start"], 16) - base
                if index + 1 < len(records)
                else end
            )
            rows.append(
                {
                    "ordinal": index,
                    "rel": start,
                    "consumed": end - start,
                    "slot": following - start,
                    "decoded": int(row["decoded_bytes"]),
                }
            )
        table[language] = rows

        if args.search:
            values = []
            for row in rows:
                values.extend(
                    (
                        ("rel", row["rel"]),
                        ("rel16", row["rel"] // 16),
                        ("slot", row["slot"]),
                        ("slot16", row["slot"] // 16),
                        ("consumed", row["consumed"]),
                        ("decoded", row["decoded"]),
                    )
                )
            hits = Counter()
            for name, value in values:
                if 0 <= value < 2**32:
                    if front_a.find(struct.pack("<I", value)) >= 0 or front_b.find(
                        struct.pack("<I", value)
                    ) >= 0:
                        hits[name] += 1
            print(f"  plaintext value hits: {dict(hits)}")

    shown = min(args.limit, min(len(rows) for rows in table.values()))
    print(f"\nfirst {shown} ordinals")
    for ordinal in range(shown):
        print(f"ordinal {ordinal}")
        for language in languages:
            row = table[language][ordinal]
            print(
                f"  {language:10} rel=0x{row['rel']:x} consumed={row['consumed']} "
                f"slot={row['slot']} decoded={row['decoded']}"
            )

    print("\npairwise equality over all ordinals")
    reference = languages[0]
    for language in languages[1:]:
        pairs = list(zip(table[reference], table[language]))
        print(
            f"{reference} vs {language}: "
            f"rel={sum(a['rel'] == b['rel'] for a, b in pairs)} "
            f"consumed={sum(a['consumed'] == b['consumed'] for a, b in pairs)} "
            f"slot={sum(a['slot'] == b['slot'] for a, b in pairs)} "
            f"decoded={sum(a['decoded'] == b['decoded'] for a, b in pairs)}"
        )
    data.close()


if __name__ == "__main__":
    main()
