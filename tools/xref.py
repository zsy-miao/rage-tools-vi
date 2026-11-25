"""Find the code that references an image RVA: call/jmp rel32, and rip-relative operands.

Disassembling 190 MB of text answers "what calls this", but only if the question is asked
first. This scans the image's executable sections for the four encodings that name a
target, and prints each hit with the bytes around it so the caller's shape is readable.

    python3 tools/xref.py cache/exe/game_scarlett_master.exe --to 0x2236e00
    python3 tools/xref.py <exe> --to 0x2236e00 --kind call --limit 20
    python3 tools/xref.py <exe> --to 0x9ab15e8 --kind data

Kinds: `call` (`e8`), `jmp` (`e9`/`0f 85`-family), `data` (rip-relative `mov`/`lea` with a
modrm that addresses memory), and `any` (all of them).
"""

import argparse
import struct
import sys
from pathlib import Path

IMAGE_BASE = 0x140000000
RIP_MODRM = frozenset((0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D))


def sections(data):
    """[(name, virtual address, raw offset, raw size, characteristics)] of the PE."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    table = pe + 24 + optional_size
    names = data[pe + 24 + 64:pe + 24 + 64 + count * 8]
    out = []
    for index in range(count):
        virtual_size, virtual, raw_size, raw = struct.unpack_from("<IIII", data, table + 40 * index + 8)
        flags = struct.unpack_from("<I", data, table + 40 * index + 36)[0]
        out.append((names[index * 8:index * 8 + 8].rstrip(b"\0").decode("ascii", "replace"),
                    virtual, raw, raw_size, flags))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("exe", type=Path)
    parser.add_argument("--to", required=True, type=lambda v: int(v, 0), help="target RVA")
    parser.add_argument("--kind", choices=("call", "jmp", "data", "any"), default="any")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()

    data = args.exe.read_bytes()
    target = args.to
    hits = []
    for name, virtual, raw, raw_size, flags in sections(data):
        if not flags & 0x20000000:  # IMAGE_SCN_MEM_EXECUTE
            continue
        body = data[raw:raw + raw_size]
        for at in range(len(body) - 4):
            rva = virtual + at
            # call rel32 / jmp rel32
            if body[at] in (0xE8, 0xE9):
                delta = struct.unpack_from("<i", body, at + 1)[0]
                if rva + 5 + delta == target:
                    hits.append((rva, "call" if body[at] == 0xE8 else "jmp", 5))
            # short conditional jumps, 0f 8x rel32
            if body[at] == 0x0F and 0x80 <= body[at + 1] <= 0x8F:
                delta = struct.unpack_from("<i", body, at + 2)[0]
                if rva + 6 + delta == target:
                    hits.append((rva, "jcc", 6))
            # rip-relative memory operand: modrm with mod=00, rm=101 (the eight reg forms)
            if body[at + 1] in RIP_MODRM:
                delta = struct.unpack_from("<i", body, at + 2)[0]
                if rva + 6 + delta == target:
                    hits.append((rva, "data", 6))
    wanted = {"call": ("call",), "jmp": ("jmp", "jcc"), "data": ("data",)}.get(args.kind, None)
    if wanted:
        hits = [hit for hit in hits if hit[1] in wanted]
    print(f"{args.exe.name}: {len(hits)} reference(s) to {target:#x}")
    for rva, kind, size in hits[:args.limit]:
        offset = None
        for name, virtual, raw, raw_size, flags in sections(data):
            if virtual <= rva < virtual + raw_size:
                offset = raw + (rva - virtual)
                break
        around = data[offset - 16:offset + size + 8] if offset else b""
        print(f"  {IMAGE_BASE + rva:#012x} ({rva:#x}) {kind:4s}  {around.hex(' ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
