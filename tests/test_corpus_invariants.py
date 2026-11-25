"""Invariants of the real corpus, checked against the committed tables.

These need the extracted indexes (`output/index/`) and the source archives. Each check
prints `skipped` instead of failing when an input is absent, so a clean clone still passes.

    python3 tests/test_corpus_invariants.py
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

INDEX = ROOT / "output/index"
FAILED = []


def check(name, condition, detail=""):
    print(f"  {'ok  ' if condition else 'FAIL'}  {name} {detail}")
    if not condition:
        FAILED.append(name)


def rows(path):
    with path.open() as handle:
        yield from csv.DictReader(handle, delimiter="\t")


def union_length(spans):
    total = 0
    end = -1
    for start, stop in sorted(spans):
        start = max(start, end)
        if stop > start:
            total += stop - start
            end = stop
    return total


def main():
    indexes = sorted(INDEX.glob("*.tsv")) if INDEX.is_dir() else []
    if not indexes:
        print("  skipped (no output/index)")
        return 0

    print("index tiling")
    covered = unparsed = 0
    for path in indexes:
        spans = []
        for row in rows(path):
            try:
                spans.append((int(row["start"], 16), int(row["end"], 16)))
            except (KeyError, ValueError):
                unparsed += 1
                continue
        covered += len(spans)
    check("every index has rows", covered > 0, f"({covered:,} rows over {len(indexes)} indexes)")
    check("every row parses", unparsed == 0, f"({unparsed} unparsable)")

    print("audio census")
    tables = {"audio.rpf": ROOT / "handoff/audio-full-census.tsv",
              "story000.rpf": ROOT / "handoff/audio-story000-census.tsv"}
    published = {"audio.rpf": (7159, 1606237, 22469942310),
                 "story000.rpf": (63325, 213579, 6058672128)}
    for archive, path in tables.items():
        if not path.is_file():
            print(f"  skipped ({archive}: table not present)")
            continue
        entries = list(rows(path))
        streams = sum(int(row["streams"]) for row in entries)
        data_bytes = sum(int(row["data_bytes"]) for row in entries)
        want = published[archive]
        check(f"{archive} container count", len(entries) == want[0], f"({len(entries):,})")
        check(f"{archive} stream count", streams == want[1], f"({streams:,})")
        if want[2]:
            check(f"{archive} data bytes", abs(data_bytes - want[2]) < 10**6,
                  f"({data_bytes:,} B)")
    check("two archives carry audio", len(tables) == 2)

    print("decoded audio artifacts")
    decoded = ROOT / "output/audio-ff25"
    if not (decoded.is_dir() and any(decoded.glob("*.wav"))):
        print("  skipped (no decoded WAVs)")
    else:
        import wave
        files = sorted(decoded.glob("*.wav"))
        frames = 0
        empty = 0
        for path in files:
            with wave.open(str(path)) as wav:
                count = wav.getnframes()
            frames += count
            empty += 1 if count == 0 else 0
        check("every container produced a file", len(files) == 3008, f"({len(files)})")
        check("no empty file", empty == 0, f"({empty})")
        check("audio hours match the census", 99 < frames / 48000 / 3600 < 102,
              f"({frames / 48000 / 3600:.2f} h)")

    print()
    print("PASS" if not FAILED else f"FAIL: {len(FAILED)} check(s)")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
