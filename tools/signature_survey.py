#!/usr/bin/env python3
"""Classify bulk-extracted streams by leading magic/signature."""
import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path

SIGNATURES = (
    (b"RSC7", "RSC7"),
    (b"RBF0", "RBF0"),
    (b"PSIN", "PSIN"),
    (b"\x42\x40", "u16_4042"),
    (b"\x0f\x00\x00\x80", "0f000080"),
    (b"9FPR", "RPF9"),
    (b"CHKS", "CHKS"),
    (b"LSCH", "LSCH"),
    (b"LENM", "LENM"),
    (b"LSNS", "LSNS"),
    (b"LRSC", "LRSC"),
    (b"DDS ", "DDS"),
    (b"DXBC", "DXBC"),
    (b"GNF ", "GNF"),
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"RIFF", "RIFF"),
    (b"OggS", "OGG"),
    (b"<?xml", "XML"),
    (b"<", "XML?"),
    (b"{\"", "JSON"),
    (b"[\"", "JSON?"),
)


def classify(blob):
    if not blob:
        return "empty", 0
    offset = 0
    while offset < len(blob) and blob[offset] == 0:
        offset += 1
    body = blob[offset:]
    if not body:
        return "zero", offset
    for magic, name in SIGNATURES:
        if body.startswith(magic):
            return name, offset
    if body[:1] == b"\x78" and len(body) > 1 and body[1] in (0x01, 0x5E, 0x9C, 0xDA):
        return "zlib", offset
    if all(32 <= byte < 127 or byte in (9, 10, 13) for byte in body):
        return "text", offset
    return "binary", offset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--details", type=Path, default=Path("output/packs-signatures.tsv"))
    parser.add_argument("--summary", type=Path, default=Path("handoff/packs-signature-summary.tsv"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--all-kinds", action="store_true")
    args = parser.parse_args()

    rows = []
    summary = defaultdict(lambda: [0, 0])
    unknown = Counter()
    with args.manifest.open(newline="", encoding="utf-8") as handle:
        for index, row in enumerate(csv.DictReader(handle, delimiter="\t")):
            if args.limit and index >= args.limit:
                break
            if not args.all_kinds and row.get("kind") not in (None, "binary"):
                continue
            path = Path(row["path"])
            try:
                with path.open("rb") as stream:
                    head = stream.read(256)
            except OSError as error:
                head = b""
            kind, offset = classify(head)
            decoded = int(row["decoded_bytes"])
            rows.append((row["start"], row["end"], decoded, kind, offset, head[:16].hex(), str(path)))
            summary[kind][0] += 1
            summary[kind][1] += decoded
            if kind in ("binary", "text", "zlib", "empty"):
                unknown[head[:8].hex()] += 1

    args.details.parent.mkdir(parents=True, exist_ok=True)
    with args.details.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["start", "end", "decoded_bytes", "kind", "nonzero_offset", "head_hex", "path"])
        writer.writerows(rows)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    with args.summary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["kind", "streams", "decoded_bytes"])
        for kind, (count, decoded) in sorted(summary.items(), key=lambda item: -item[1][0]):
            writer.writerow([kind, count, decoded])
    print("kind\tstreams\tdecoded_bytes")
    for kind, (count, decoded) in sorted(summary.items(), key=lambda item: -item[1][0]):
        print(f"{kind}\t{count}\t{decoded}")
    print("top unknown heads", unknown.most_common(8))


if __name__ == "__main__":
    main()
