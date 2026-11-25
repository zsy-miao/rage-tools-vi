"""Enumerate vtables in the executable and resolve chosen slots.

A vtable is a run of 8-byte pointers into the code section inside the read-only
data. This finds those runs, reports how many slots each has, and can resolve a
slot (default `+0x60`, the stream `Read`) to the function it points at.

The point is to stop guessing which class a call site belongs to: given a slot
offset, this lists every class that could be the callee.

    python3 tools/vtable_scan.py --slot 0x60
    python3 tools/vtable_scan.py --min-slots 40 --limit 20
    python3 tools/vtable_scan.py --find 0x1462fd480
"""

import argparse
import struct
import sys
from pathlib import Path

EXE = Path("cache/exe/game_scarlett_master.exe")


class PE:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        d = self.data
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        self.image_base = struct.unpack_from("<Q", d, pe + 48)[0]
        nsec = struct.unpack_from("<H", d, pe + 6)[0]
        table = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
        self.sections = []
        for index in range(nsec):
            off = table + 40 * index
            name = d[off:off + 8].rstrip(b"\0").decode(errors="replace")
            vsize, vaddr, raw_size, raw_ptr = struct.unpack_from("<IIII", d, off + 8)
            self.sections.append({"name": name, "vaddr": self.image_base + vaddr,
                                  "vsize": vsize, "raw_ptr": raw_ptr,
                                  "raw_size": raw_size})

    def section(self, name):
        return next(s for s in self.sections if s["name"] == name)

    def is_code(self, value):
        text = self.section(".text")
        return text["vaddr"] <= value < text["vaddr"] + text["raw_size"]

    def is_rdata(self, value):
        rdata = self.section(".rdata")
        return rdata["vaddr"] <= value < rdata["vaddr"] + rdata["raw_size"]


def vtables(pe, min_slots=8):
    """Maximal runs of code pointers inside .rdata."""
    rdata = pe.section(".rdata")
    blob = pe.data[rdata["raw_ptr"]:rdata["raw_ptr"] + rdata["raw_size"]]
    out = []
    index = 0
    count = len(blob) // 8
    while index < count:
        value = struct.unpack_from("<Q", blob, index * 8)[0]
        if not pe.is_code(value):
            index += 1
            continue
        start = index
        while index < count:
            value = struct.unpack_from("<Q", blob, index * 8)[0]
            if not pe.is_code(value):
                break
            index += 1
        slots = index - start
        if slots >= min_slots:
            out.append((rdata["vaddr"] + start * 8, slots, blob, start))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--exe", type=Path, default=EXE)
    parser.add_argument("--slot", type=lambda v: int(v, 0), default=0x60,
                        help="slot byte offset to resolve (default 0x60)")
    parser.add_argument("--min-slots", type=int, default=8)
    parser.add_argument("--limit", type=int, default=40)
    parser.add_argument("--find", type=lambda v: int(v, 0),
                        help="report the vtable containing this address")
    args = parser.parse_args()

    pe = PE(args.exe)
    table = vtables(pe, args.min_slots)
    print(f"vendor tables with at least {args.min_slots} slots: {len(table)}")
    if args.find:
        for va, slots, _blob, start in table:
            if va <= args.find < va + slots * 8:
                entry = (args.find - va) // 8
                print(f"  {args.find:#x} is slot {entry} (+0x{entry*8:x}) of "
                      f"vtable {va:#x} ({slots} slots)")
                return 0
        print(f"  {args.find:#x} is not inside a detected vtable")
        return 1

    shown = 0
    for va, slots, blob, start in sorted(table, key=lambda row: -row[1]):
        index = args.slot // 8
        target = None
        if index < slots:
            target = struct.unpack_from("<Q", blob, (start + index) * 8)[0]
        if target is not None:
            print(f"  vtable {va:#12x}  slots {slots:4d}  +0x{args.slot:x} -> {target:#x}")
            shown += 1
        if shown >= args.limit:
            break
    if not shown:
        print(f"  no vtable is long enough to have a +0x{args.slot:x} slot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
