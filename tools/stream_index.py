#!/usr/bin/env python3
"""Streaming mmap range index with bounded per-stream memory."""
import argparse
import csv
import mmap
import re
import resource
import struct
import time
import zlib
from collections import Counter
from pathlib import Path

PATTERN = re.compile(rb"\x78[\x01\x5e\x9c\xda]")
CHUNK = 65536


def word(header, offset):
    return struct.unpack_from("<I", header, offset)[0]


def decode(mm, start, size):
    obj = zlib.decompressobj()
    consumed = 0
    decoded = 0
    while not obj.eof:
        block = mm[start + consumed:min(size, start + consumed + CHUNK)]
        if not block:
            return None
        try:
            decoded += len(obj.decompress(block))
        except zlib.error:
            return None
        if obj.eof:
            consumed += len(block) - len(obj.unused_data)
            break
        consumed += len(block)
    return consumed, decoded


def all_zero(mm, start, end):
    step = 1 << 20
    for pos in range(start, end, step):
        if any(mm[pos:min(end, pos + step)]):
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--madvise-every", type=int, default=2000)
    args = parser.parse_args()

    with args.archive.open("rb") as handle:
        mm = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        size = len(mm)
        front_end = word(mm, 4)
        trailer_bytes = word(mm, 12)
        trailer_start = size - trailer_bytes
        spans = [("front", 0, front_end, front_end, 0, 0)]
        cursor = front_end
        pos = front_end
        streams = 0
        started = time.monotonic()
        while pos < trailer_start:
            match = PATTERN.search(mm, pos)
            if not match:
                break
            start = match.start()
            if start % 16 or start < cursor:
                pos = start + 1
                continue
            result = decode(mm, start, trailer_start)
            if result is None:
                pos = start + 1
                continue
            stored, decoded = result
            end = start + stored
            if end > trailer_start:
                pos = start + 1
                continue
            if start > cursor:
                kind = "zero_run" if all_zero(mm, cursor, start) else "unclassified"
                spans.append((kind, cursor, start, start - cursor, 0, 0))
            # A 64 KiB chunk continues the previous chain when the next stream
            # starts on the align16 boundary of its end.  Inherit the chain's
            # start so continuations can be grouped back into one entry.
            chain_start = start
            if (
                spans
                and spans[-1][0] == "zlib"
                and spans[-1][4] == CHUNK
                and start == (spans[-1][2] + 15) // 16 * 16
            ):
                chain_start = spans[-1][5] or spans[-1][1]
            spans.append(("zlib", start, end, stored, decoded, chain_start))
            cursor = end
            pos = end
            streams += 1
            if args.madvise_every and streams % args.madvise_every == 0 and hasattr(mm, "madvise"):
                try:
                    mm.madvise(mmap.MADV_DONTNEED)
                except OSError:
                    pass
        if cursor < trailer_start:
            kind = "zero_run" if all_zero(mm, cursor, trailer_start) else "unclassified"
            spans.append((kind, cursor, trailer_start, trailer_start - cursor, 0, 0))
        spans.append(("trailer", trailer_start, size, size - trailer_start, 0, 0))
        mm.close()

    elapsed = time.monotonic() - started
    total = sum(span[3] for span in spans)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(["kind", "start", "end", "stored_bytes", "decoded_bytes", "chain_start"])
            for kind, start, end, stored, decoded, chain_start in spans:
                writer.writerow([
                    kind, f"0x{start:x}", f"0x{end:x}", stored, decoded or "",
                    f"0x{chain_start:x}" if kind == "zlib" else "",
                ])
    counts = Counter(span[0] for span in spans)
    decoded = sum(span[4] for span in spans)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(
        f"spans={len(spans)} stored={total} zlib={streams} decoded={decoded} "
        f"unclassified={counts['unclassified']} elapsed={elapsed:.2f}s rss_kb={rss} "
        f"counts={dict(counts)}"
    )
    assert total == size, (total, size)


if __name__ == "__main__":
    main()
