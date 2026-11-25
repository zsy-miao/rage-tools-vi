"""Exactly which audio streams are still undecoded.

Joins the framing tables (every stream, with its codec) against the three decode
tables (Opus, XMA2, ACE1) and reports the remainder grouped by codec and variant.
Paths differ between the tables — some absolute, some relative — so the join is on
the file's basename plus the stream index.

    python3 tools/audio_gap.py
"""
import csv
import os
from collections import Counter
from pathlib import Path

FRAMING = ["handoff/audio-awc-framing.tsv", "handoff/story000-awc-framing.tsv"]
DECODED = ["handoff/audio-opus-decode.tsv", "handoff/audio-xma2-decode.tsv",
           "handoff/audio-ace1-decode.tsv", "handoff/audio-variant-decode.tsv"]
CODECS = {"0x0b": "Opus", "0x05": "XMA2", "0x02": "ACE1"}


def key(row):
    # decode tables name the source in `path`; the variant manifest in `container`
    source = row.get("path") or row.get("container", "")
    return os.path.basename(source), row["stream"]


def main():
    framing = []
    for path in FRAMING:
        handle = Path(path)
        if handle.is_file():
            framing += list(csv.DictReader(handle.open(), delimiter="\t"))
    done = set()
    for path in DECODED:
        handle = Path(path)
        if not handle.is_file():
            continue
        for row in csv.DictReader(handle.open(), delimiter="\t"):
            if not row.get("error"):
                done.add(key(row))

    missing = [row for row in framing if key(row) not in done]
    print(f"streams in framing tables : {len(framing):,}")
    print(f"decoded                   : {len(framing) - len(missing):,}")
    print(f"undecoded                 : {len(missing):,} "
          f"in {len({key(row)[0] for row in missing}):,} files")
    print("by codec :", {CODECS.get(c, c): n
                         for c, n in Counter(r["codec"] for r in missing).most_common()})
    print("by variant:", dict(Counter(r["flags"] for r in missing).most_common()))
    print("by codec and variant:",
          {(CODECS.get(c, c), f): n for (c, f), n in
           Counter((r["codec"], r["flags"]) for r in missing).most_common()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
