"""Harvest a name corpus from decoded archive streams.

Every zlib stream in an archive is decoded and, if it looks textual, mined for
candidate names: quoted strings, path-like tokens, and XML attribute values.
The result is written one token per line, sorted and deduplicated, so hash tests
can run against the archive's own vocabulary instead of a stand-in list.

Typical use is the local `common.rpf`, whose 259 XML documents carry content
manifests, level manifests, changeset paths and setup data.
"""

import argparse
import csv
import re
import zlib
from pathlib import Path

TOKEN = re.compile(rb"[A-Za-z0-9_./:\\-]{3,120}")
QUOTED = re.compile(rb"[\"']([^\"'<>\n]{3,200})[\"']")


def looks_textual(data):
    if not data:
        return False
    sample = data[:4096]
    printable = sum(1 for byte in sample if 32 <= byte < 127 or byte in (9, 10, 13))
    return printable / len(sample) > 0.9


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("cache/name-corpus.txt"))
    parser.add_argument("--min-length", type=int, default=3)
    args = parser.parse_args()

    streams = [(int(row["start"], 16), int(row["end"], 16))
               for row in csv.DictReader(args.index.open(), delimiter="\t")
               if row["kind"] == "zlib"]
    print(f"{args.archive.name}: {len(streams)} zlib streams")

    names = set()
    textual = 0
    with args.archive.open("rb") as handle:
        import mmap
        mm = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        for start, end in streams:
            try:
                data = zlib.decompress(mm[start:end])
            except zlib.error:
                continue
            if not looks_textual(data):
                continue
            textual += 1
            for match in QUOTED.finditer(data):
                names.add(match.group(1).decode("utf-8", "ignore"))
            for match in TOKEN.finditer(data):
                names.add(match.group(0).decode("utf-8", "ignore"))
        mm.close()

    names = {name.strip() for name in names if len(name.strip()) >= args.min_length}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(sorted(names)) + "\n")
    print(f"textual streams: {textual}, distinct tokens: {len(names)}")
    print(f"wrote {args.out}")
    sample = sorted(names)[:8]
    print("sample:", sample)


if __name__ == "__main__":
    main()
