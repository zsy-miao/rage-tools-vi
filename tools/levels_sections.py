"""Census the tagged sections of `levels`-style PSIN records.

`script.rpf` records carry five PSIN blocks with nearly constant tags. `levels`
records use the same chunk chain (`PSIN LSCH LENM LSNS LGID LRSC CHKS`) but a
different PSIN payload: a 16-byte `(count, count, 2, 0)` directory plus one block
per *content section*, each with its own tag. The tags are stable across records
even though which sections appear depends on the level.

This reports, per tag: how many records carry it, its length range, its dominant
length, whether the payload is printable ASCII, and one sample.

    python3 tools/levels_sections.py --archive /path/levels.rpf \\
        --index output/index/levels.tsv --limit 500
"""

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import script_meta as sm
import psin_blocks as pb

DIRECTORY_TAG = 0xD56F1E2C


def printable(payload):
    # the serializer fills with 0x70, so trailing 0x70 and NUL padding are not text
    text = payload.rstrip(b"\0\x70")
    if not text:
        return False
    good = sum(1 for byte in text if 32 <= byte < 127 or byte in (9, 10, 13))
    return good / len(text) > 0.95


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--top", type=int, default=25)
    args = parser.parse_args()

    records = 0
    tags = Counter()
    lengths = defaultdict(Counter)
    samples = {}
    ascii_tags = Counter()
    descriptors = Counter()

    for record, body in sm.streams(args.archive, args.index):
        parsed = sm.parse_psin(body, 0)
        if not parsed:
            continue
        records += 1
        descriptors[parsed["count"]] += 1
        for tag, payload in pb.blocks(body):
            tags[tag] += 1
            lengths[tag][len(payload)] += 1
            if tag not in samples:
                samples[tag] = payload[:48]
            if printable(payload):
                ascii_tags[tag] += 1
        if args.limit and records >= args.limit:
            break

    print(f"records {records}")
    print("descriptors per record:", descriptors.most_common(8))
    print(f"distinct section tags: {len(tags)}\n")
    print(f"{'tag':>10s} {'records':>7s} {'ascii':>6s} {'min':>6s} {'max':>8s} "
          f"{'common length':>14s}  sample")
    for tag, count in tags.most_common(args.top):
        length_counter = lengths[tag]
        common, _ = length_counter.most_common(1)[0]
        sample = samples[tag]
        text = sample.rstrip(b"\0")
        shown = (text[:40].decode("ascii", "replace") if ascii_tags[tag] else sample[:16].hex())
        print(f"0x{tag:08x} {count:7d} {ascii_tags[tag]:6d} {min(length_counter):6d} "
              f"{max(length_counter):8d} {common:14d}  {shown}")
    directory = lengths.get(DIRECTORY_TAG)
    if directory:
        print(f"\ndirectory tag 0x{DIRECTORY_TAG:08x}: lengths {directory.most_common(6)}")


if __name__ == "__main__":
    raise SystemExit(main())
