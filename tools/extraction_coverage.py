#!/usr/bin/env python3
"""Summarize repo-wide extraction coverage and unsupported spans."""
import argparse
import csv
from collections import defaultdict
from pathlib import Path

ARCHIVES = (
    Path("data.rpf"), Path("common.rpf"), Path("script.rpf"),
    Path("story000_bvh4.rpf"), Path("appdata0.rpf"),
    Path("core_licenses_data.rpf"), Path("shaders.rpf"), Path("textures.rpf"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventories", type=Path, nargs="*", default=[
        Path("output/extraction-inventory.tsv"), Path("output/archive-maps.tsv"),
    ])
    parser.add_argument("--md", type=Path, default=Path("handoff/extraction-coverage.md"))
    parser.add_argument("--tsv", type=Path, default=Path("handoff/extraction-coverage-summary.tsv"))
    args = parser.parse_args()

    totals = defaultdict(lambda: [0, 0, 0])
    kinds = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    for path in args.inventories:
        if not path.is_file():
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                archive = row["archive"]
                stored = int(row["stored_bytes"])
                decoded = int(row["decoded_bytes"] or 0)
                totals[archive][0] += 1
                totals[archive][1] += stored
                totals[archive][2] += decoded
                kinds[archive][row["kind"]][0] += 1
                kinds[archive][row["kind"]][1] += stored
                kinds[archive][row["kind"]][2] += decoded

    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    args.md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Extraction coverage",
        "",
        "Repo-wide normalized inventory. Full means every stored byte has a range;",
        "partial means only known subranges are inventoried; deferred means the",
        "archive is intentionally not scanned yet.",
        "",
        "| Archive | File bytes | Ranges | Mapped bytes | Coverage | Decoded bytes | Unclassified | Status |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    with args.tsv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["archive", "file_bytes", "ranges", "mapped_bytes", "coverage", "decoded_bytes", "unclassified_bytes", "status"])
        for archive in ARCHIVES:
            name = archive.name
            file_bytes = archive.stat().st_size if archive.is_file() else 0
            count, stored, decoded = totals.get(name, [0, 0, 0])
            unclassified = kinds.get(name, {}).get("unclassified", [0, 0, 0])[1]
            coverage = stored / file_bytes if file_bytes else 0.0
            if count == 0:
                status = "deferred"
            elif stored == file_bytes:
                status = "full"
            else:
                status = "partial"
            writer.writerow([
                name, file_bytes, count, stored, f"{coverage:.6f}", decoded,
                unclassified, status,
            ])
            lines.append(
                f"| `{name}` | {file_bytes:,} | {count:,} | {stored:,} | "
                f"{coverage:.2%} | {decoded:,} | {unclassified:,} | {status} |"
            )

    lines += [
        "",
        "## Unsupported bytes",
        "",
        "`unclassified` ranges preserve bytes but do not have authoritative entry",
        "names or decoded semantics. Front/trailer regions are preserved as",
        "metadata evidence; zero runs are verified padding. `shaders.rpf` and",
        "`textures.rpf` are deferred because their full `map` scans are large.",
        "",
        "## Commands",
        "",
        "```bash",
        "python3 tools/extraction_inventory.py",
        "python3 tools/archive_inventory.py",
        "python3 tools/extraction_coverage.py",
        "```",
    ]
    args.md.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
