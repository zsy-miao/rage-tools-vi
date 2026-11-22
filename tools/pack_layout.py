"""Draw one pack's front-region map from its own header, using the loader's formula.

    python3 tools/pack_layout.py data.rpf --offset 0
    python3 tools/pack_layout.py /path/levels.rpf --scan 5

The sections come from `FUN_14087aff0` in the executable: the four arena sections
are sizes the code computes, and everything after them up to `word_04` is a region
the traced code does not name. Buffer B is a *suffix* of that (buffer A is the whole
front region and B is re-read from `word_08`), so the map shows it inside A.
"""

import argparse
import struct
import sys
from pathlib import Path


def align(value, step):
    return (value + step - 1) // step * step


def header_at(path, offset):
    with path.open("rb") as handle:
        handle.seek(offset)
        header = handle.read(0x60)
    if len(header) < 0x60 or header[:4] != b"9FPR":
        return None
    fields = struct.unpack_from("<12I", header, 0)
    front_end, block, trailer = fields[1], fields[2], fields[3]
    p3 = struct.unpack_from("<H", header, 0x1A)[0]
    p4 = struct.unpack_from("<I", header, 0x1C)[0]
    p5 = struct.unpack_from("<H", header, 0x20)[0]
    p6 = struct.unpack_from("<H", header, 0x22)[0]
    count = fields[9]
    p8 = header[0x2C]
    flag = header[0x2D] & 1
    return {"front_end": front_end, "block": block, "trailer": trailer,
            "mode": fields[8], "count": count, "p3": p3, "p4": p4, "p5": p5,
            "p6": p6, "p8": p8, "align": 16 if flag else 4}


def layout(fields):
    step = fields["align"]
    p3, p4, p5, p6 = fields["p3"], fields["p4"], fields["p5"], fields["p6"]
    count, p8 = fields["count"], fields["p8"]
    offsets = [alignment for alignment in (align(0x40, step),)]
    offsets.append(align(offsets[-1] + p3 * 8, step))
    offsets.append(align(offsets[-1] + p4, step))
    offsets.append(align(offsets[-1] + p5 * 0x18, step))
    offsets.append(align(offsets[-1] + (p5 - p6) * count * p8, 8))
    offsets.append(align(offsets[-1], 16))
    return offsets


def draw(path, offset, fields, out=sys.stdout):
    offsets = layout(fields)
    end = fields["front_end"]
    block = fields["block"]
    print(f"\n{path.name}+0x{offset:x}", file=out)
    print(f"  mode 0x{fields['mode']:08x}  N={fields['count']}  "
          f"p3={fields['p3']} p4={fields['p4']} p5={fields['p5']} "
          f"p6={fields['p6']} p8={fields['p8']}", file=out)
    print(f"  word_04 (front size) {end:#x}   word_08 (B start) {block:#x}   "
          f"trailer {fields['trailer']:#x}", file=out)
    labels = ["header", "section1", "section2", "section3", "section4"]
    spans = [(0x00, offsets[0], "header 0x40"),
             (offsets[0], offsets[1], f"section1 {fields['p3']}x8"),
             (offsets[1], offsets[2], f"section2 {fields['p4']} B"),
             (offsets[2], offsets[3], f"section3 {fields['p5']}x24"),
             (offsets[3], offsets[4],
              f"section4 ({fields['p5']}-{fields['p6']})x{fields['count']}x{fields['p8']}"),
             (offsets[4], end, "unnamed remainder (B is its suffix)")]
    for index, (start, stop, label) in enumerate(spans):
        bar = "#" * max(1, int(60 * (stop - start) / end))
        print(f"  {start:#07x} {stop:#07x} {stop - start:8d}  {bar:<60s} {label}", file=out)
    print(f"  buffer B {block:#x}..{end:#x} = {end - block} bytes "
          f"({(end - block) / fields['count']:.2f} per entry)", file=out)
    if offsets[5] > end:
        print("  WARNING: the arena overruns the buffer", file=out)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("data.rpf"))
    parser.add_argument("--offset", type=lambda v: int(v, 0), default=0)
    parser.add_argument("--scan", type=int, default=0, help="draw the first N headers")
    args = parser.parse_args()

    if not args.archive.is_file():
        sys.exit(f"missing {args.archive}")
    if args.scan:
        size = args.archive.stat().st_size
        shown = 0
        for offset in range(0, max(0, size - 0x60), 0x4000):
            fields = header_at(args.archive, offset)
            if not fields:
                continue
            draw(args.archive, offset, fields)
            shown += 1
            if shown >= args.scan:
                break
        return 0
    fields = header_at(args.archive, args.offset)
    if not fields:
        sys.exit("no 9FPR header at that offset")
    draw(args.archive, args.offset, fields)
    return 0


if __name__ == "__main__":
    sys.exit(main())
