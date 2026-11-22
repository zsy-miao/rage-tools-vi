#!/usr/bin/env python3
"""Inventory a source directory and locate extracted manifests for its RPFs."""

import argparse
import csv
from filecmp import cmp
import json
from pathlib import Path
from urllib.parse import quote

from extraction_tree import HTML


def write_tree(rows, output):
    directories = {Path("."): []}
    for relative, size, magic, manifest, stream_index in rows:
        for parent in reversed(relative.parents):
            if parent not in directories:
                children = []
                directories[parent] = children
                directories[parent.parent].append({"name": parent.name, "kind": "Pasta",
                                                   "children": children})
        item = {"name": relative.name, "kind": "RPF9" if magic == "39465052" else "Arquivo",
                "source": str(relative), "stored": size}
        if manifest:
            item["manifest"] = str(manifest)
        if stream_index:
            item["stream_index"] = quote(stream_index.relative_to(output).as_posix())
        directories[relative.parent].append(item)
    data = json.dumps(directories[Path(".")], ensure_ascii=True).replace("<", "\\u003c")
    (output / "index.html").write_text(HTML.replace("__ARCHIVES__", data), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("output/downloads-corpus"))
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_dir():
        parser.error("source must be an existing directory")
    output = args.output.resolve()
    if output.is_relative_to(source):
        parser.error("choose an output directory outside the source")
    repo = Path(__file__).resolve().parents[1]
    rows = []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        magic = ""
        manifest = None
        stream_index = None
        if path.suffix.lower() == ".rpf":
            with path.open("rb") as reader:
                magic = reader.read(4).hex()
            local = output / relative / "ranges.tsv"
            index = output / "indexes" / relative.with_suffix(".tsv")
            if index.is_file():
                stream_index = index
            sample = repo / path.name
            previous = repo / "output/general-extraction" / path.name / "ranges.tsv"
            if local.is_file():
                manifest = local
            elif previous.is_file() and sample.is_file() and cmp(path, sample, shallow=False):
                manifest = previous
        rows.append((relative, path.stat().st_size, magic, manifest or "", stream_index or ""))
    output.mkdir(parents=True, exist_ok=True)
    with (output / "inventory.tsv").open("w", encoding="utf-8", newline="") as out:
        writer = csv.writer(out, delimiter="\t", lineterminator="\n")
        writer.writerow(("relative_path", "stored_bytes", "rpf_magic_hex", "extraction_manifest", "stream_index"))
        writer.writerows(rows)
    write_tree(rows, output)
    print(f"{len(rows)} source files, {sum(bool(row[2]) for row in rows)} RPFs, "
          f"{sum(bool(row[3]) for row in rows)} extraction manifests, "
          f"{sum(bool(row[4]) for row in rows)} stream indexes")


if __name__ == "__main__":
    main()
