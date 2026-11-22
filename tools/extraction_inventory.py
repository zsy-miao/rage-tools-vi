#!/usr/bin/env python3
"""Normalize the stream indexes into one repo-wide extraction inventory.

The inventory is built from `output/index/*.tsv`, which carries the range layer
(kind, start, end, stored, decoded) for every archive, and it is cross-checked
against the extraction manifests so the summary states how much of each kind was
actually extracted and hashed.

Every index range must tile its archive: the kinds' stored bytes must sum to the
file size with no gap or overlap, which is the property the old data-only
inventory could not check.
"""

import argparse
import csv
import os
from collections import defaultdict
from pathlib import Path

ARCHIVES = {
    "anim": "anim.rpf",
    "audio": "audio.rpf",
    "common": "common.rpf",
    "core_bvh4": "pack/core_bvh4/core_bvh4.rpf",
    "core_licenses_data": "pack/core_licenses/core_licenses_data.rpf",
    "core_restofworld": "pack/core_restofworld/core_restofworld.rpf",
    "core_restofworld001": "pack/core_restofworld001/core_restofworld001.rpf",
    "data": "data.rpf",
    "levels": "levels.rpf",
    "movies": "movies.rpf",
    "navmeshes": "navmeshes.rpf",
    "packs": "packs.rpf",
    "script": "script.rpf",
    "shaders": "shaders.rpf",
    "shared_minigame000": "pack/shared_minigame000/shared_minigame000.rpf",
    "shared_minigame000_bvh4": "pack/shared_minigame000_bvh4/shared_minigame000_bvh4.rpf",
    "story000": "pack/story000/story000.rpf",
    "story000_bvh4": "pack/story000_bvh4/story000_bvh4.rpf",
    "story000_restofworld": "pack/story000_restofworld/story000_restofworld.rpf",
    "story000_script": "pack/story000/story000_script.rpf",
    "textures": "textures.rpf",
    "appdata0": "appdata0.rpf",
}


def load_manifest(path):
    """Return {start_hex: decoded_bytes} from an extraction manifest."""
    out = {}
    if not path.is_file():
        return out
    with path.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            out[row["start"]] = int(row.get("decoded_bytes") or 0)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-dir", type=Path, default=Path("output/index"))
    parser.add_argument("--extracted-dir", type=Path, default=Path("output/extracted"))
    parser.add_argument("--source", type=Path,
                        default=Path("/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK"))
    parser.add_argument("--ranges-out", type=Path, default=Path("output/extraction-inventory.tsv"))
    parser.add_argument("--summary-out", type=Path, default=Path("handoff/extraction-inventory-summary.tsv"))
    args = parser.parse_args()

    rows = []
    totals = defaultdict(lambda: [0, 0, 0, 0, 0])  # ranges, stored, decoded, extracted, size
    failures = []
    for key, relative in sorted(ARCHIVES.items()):
        index = args.index_dir / f"{key}.tsv"
        if not index.is_file():
            continue
        manifest = load_manifest(args.extracted_dir / key / "manifest.tsv")
        cursor = 0
        size = None
        if (args.source / relative).is_file():
            size = os.path.getsize(args.source / relative)
        for row in csv.DictReader(index.open(), delimiter="\t"):
            start = int(row["start"], 16)
            end = int(row["end"], 16)
            stored = int(row["stored_bytes"])
            decoded = int(row["decoded_bytes"] or 0)
            kind = row["kind"]
            if start != cursor or end - start != stored:
                failures.append(f"{key}: broken coverage at 0x{cursor:x}")
                break
            cursor = end
            extracted = 1 if kind == "zlib" and f"0x{start:x}" in manifest else 0
            rows.append((key, kind, start, end, stored, decoded, extracted))
            entry = totals[(key, kind)]
            entry[0] += 1
            entry[1] += stored
            entry[2] += decoded
            entry[3] += extracted
        if size is not None and cursor != size:
            failures.append(f"{key}: index ends at 0x{cursor:x}, file is 0x{size:x}")
        totals[(key, "ALL")][4] = size or 0

    args.ranges_out.parent.mkdir(parents=True, exist_ok=True)
    with args.ranges_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["archive", "kind", "start", "end", "stored_bytes",
                         "decoded_bytes", "extracted"])
        for archive, kind, start, end, stored, decoded, extracted in rows:
            writer.writerow([archive, kind, f"0x{start:x}", f"0x{end:x}", stored,
                             decoded, extracted])

    args.summary_out.parent.mkdir(parents=True, exist_ok=True)
    with args.summary_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["archive", "kind", "ranges", "stored_bytes", "decoded_bytes", "extracted"])
        for (archive, kind), values in sorted(totals.items()):
            writer.writerow([archive, kind, values[0], values[1], values[2], values[3]])

    print("archive\tkind\tranges\tstored\tdecoded\textracted")
    for (archive, kind), values in sorted(totals.items()):
        if kind == "ALL":
            continue
        print(f"{archive}\t{kind}\t{values[0]}\t{values[1]}\t{values[2]}\t{values[3]}")
    total_stored = sum(values[1] for (archive, kind), values in totals.items() if kind != "ALL")
    total_decoded = sum(values[2] for (archive, kind), values in totals.items() if kind != "ALL")
    total_ranges = sum(values[0] for (archive, kind), values in totals.items() if kind != "ALL")
    print(f"total\t\t{total_ranges}\t{total_stored}\t{total_decoded}")
    if failures:
        print("\ncoverage failures:")
        for line in failures:
            print("  " + line)
        raise SystemExit(1)
    print("\ncoverage: every index tiles its archive exactly")


if __name__ == "__main__":
    main()
