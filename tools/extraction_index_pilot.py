#!/usr/bin/env python3
"""Build a standalone RPF range browser from the eight rebuilt indexes."""

import argparse
import csv
import hashlib
from itertools import chain, islice
import json
from pathlib import Path

from extraction_tree import HTML


OUTPUT = Path("output")
ARCHIVES = ("audio", "anim", "core_bvh4", "levels", "movies", "navmeshes", "packs", "story000")


def index_only_archives():
    """Archives without an extraction manifest stay index-only.

    Derived from the output tree so finishing an extraction promotes the
    archive without editing this file.
    """
    return {
        key for key in ARCHIVES
        if not (OUTPUT / f"extracted/{key}/manifest.tsv").exists()
    }
VERIFICATION = OUTPUT / "verification.tsv"
PAGE_SIZE = 32


def rows(path):
    with path.open(encoding="utf-8", newline="") as source:
        yield from csv.DictReader(source, delimiter="\t")


def extent(row):
    return tuple(int(row[field], 16) for field in ("start", "end"))


def index_pages(path, full):
    if full:
        records = list(rows(path))
        return len(records), [(0, records)] if records else []

    with path.open("rb") as source:
        total = sum(1 for _ in source) - 1
    if total <= 0:
        return 0, []

    starts = sorted({0, max(0, (total - PAGE_SIZE) // 2), max(0, total - PAGE_SIZE)})
    pages = []
    cursor = 0
    with path.open(encoding="utf-8", newline="") as source:
        header = source.readline()
        for start in starts:
            stop = min(total, start + PAGE_SIZE)
            start = max(start, cursor)
            if start >= stop:
                continue
            lines = islice(source, start - cursor, stop - cursor)
            page = list(csv.DictReader(chain((header,), lines), delimiter="\t"))
            if len(page) != stop - start:
                raise ValueError(f"Index changed during sampling: {path}")
            pages.append((start, page))
            cursor = stop
    return total, pages


def verification_record(name, verification):
    """The PASS verification row for an archive, or None when it has none.

    Verification tables are rebuilt per archive, so an archive can legitimately be
    missing from one (or appear more than once while a run is in progress). A
    missing row is not a failure of the browser: the archive is shown as indexed
    only, which is what the data supports.
    """
    matches = [row for row in verification if Path(row["archive"]).name == name]
    if not matches:
        return None
    if len(matches) > 1:
        matches = [row for row in matches if row.get("status") == "PASS"] or matches[-1:]
    record = matches[0]
    if (record["status"] != "PASS" or int(record["manifest"]) != int(record["index"])
            or any(int(record[field]) for field in ("missing", "extra", "failures"))):
        raise ValueError(f"Manifest lacks matching PASS verification for {name}")
    return record


def match_manifest(path, pages, expected_count):
    expected = {extent(row): row for _, page in pages for row in page if row["kind"] == "zlib"}
    matched = {}
    count = 0
    for extracted in rows(path):
        count += 1
        key = extent(extracted)
        if key not in expected:
            continue
        if key in matched or any(
            int(expected[key][field]) != int(extracted[field])
            for field in ("stored_bytes", "decoded_bytes")
        ):
            raise ValueError(f"Index and manifest disagree at {key[0]:#x} in {path}")
        matched[key] = extracted
    if count != expected_count or matched.keys() != expected.keys():
        raise ValueError(f"Verification count or sampled zlib extents disagree with {path}")
    return matched


def range_item(row, archive, manifest, extracted):
    start, end = extent(row)
    status = "Unresolved" if row["kind"] == "unclassified" else "Indexed only"
    item = {
        "name": f"{start:#x}–{end:#x}",
        "kind": f"{status} · {row['kind']}",
        "start": start,
        "end": end,
        "stored": int(row["stored_bytes"]),
        "decoded": int(row["decoded_bytes"] or 0),
        "source": archive,
        "availability": "No extracted file is listed for this range.",
    }
    if extracted:
        item.update(kind=f"Decoded / verified · {row['kind']}",
                    file=extracted["path"], sha256=extracted["sha256"],
                    manifest=str(manifest), availability="")
    return item


def verify_control(name, page_items):
    control = next(item for _, page in page_items for item in page if "sha256" in item)
    path = Path(control["file"])
    with path.open("rb") as payload:
        actual = hashlib.file_digest(payload, "sha256").hexdigest()
    if path.stat().st_size != control["decoded"] or actual != control["sha256"]:
        raise ValueError(f"{name} control failed size/hash verification: {path}")
    print(f"{name} {control['name']} matched the decoded file and SHA-256 {actual}")


def archive_root(key, verification):
    name = f"{key}.rpf"
    index = OUTPUT / f"index/{key}.tsv"
    manifest = OUTPUT / f"extracted/{key}/manifest.tsv"
    full = key == "audio"
    total, pages = index_pages(index, full)
    if not pages:
        raise ValueError(f"Index is empty: {index}")
    if key in index_only_archives():
        if manifest.exists():
            raise ValueError(f"Index-only archive now has an extraction manifest: {manifest}")
        source, matched, status = name, {}, "Indexed only"
    else:
        record = verification_record(name, verification)
        if record is None:
            source, status, matched = name, "Indexed only (no verification row)", {}
        else:
            source, status = record["archive"], "Verified archive"
            matched = match_manifest(manifest, pages, int(record["manifest"]))

    page_items = [
        (start, [range_item(row, source, manifest, matched.get(extent(row))) for row in page])
        for start, page in pages
    ]
    if matched:
        verify_control(name, page_items)
    shown = sum(len(page) for _, page in page_items)
    print(f"{name}: {shown:,} of {total:,} index ranges shown, {len(matched):,} verified rows shown")

    root = {"name": name, "ranges": total}
    if full:
        return dict(root, kind=f"{status} · all indexed ranges", children=page_items[0][1])
    return dict(
        root,
        kind=f"{status} · bounded sample",
        children=[
            {"name": f"Index rows {start + 1:,}–{start + len(page):,}",
             "kind": "Sample page", "children": page}
            for start, page in page_items
        ],
        note=f"Showing {shown:,} of {total:,} index ranges in bounded sample pages. "
             f"Full index: {index}. Pack membership is unresolved.",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT / "extraction-index-pilot/index.html")
    args = parser.parse_args()
    verification = list(rows(VERIFICATION))
    roots = [archive_root(key, verification) for key in ARCHIVES]
    data = json.dumps(roots, separators=(",", ":"), ensure_ascii=True).replace("<", "\\u003c")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(HTML.replace("__ARCHIVES__", data), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
