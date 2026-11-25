"""Name every indirect call through an import: `call [rip+x]` -> which library, which symbol.

A backtrace gives addresses inside the image; what it does not give is which imported CRT or
system function the failing frame had just called. This maps the import address table to names
first, then scans the executable sections for the two encodings that call through it
(`ff 15` for call, `ff 25` for jmp), and answers two questions:

    python3 tools/iat_calls.py <exe> --at 0x2240EFC        # the calls near an address
    python3 tools/iat_calls.py <exe> --symbol memmove      # every site that calls it
    python3 tools/iat_calls.py <exe> --at 0x2240EFC --window 0x4000

`--at` prints the calls in the window before the address, nearest last, which is how the
import a frame used is identified without a disassembler.
"""

import argparse
import struct
import sys
from pathlib import Path

IMAGE_BASE = 0x140000000


def sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    table = pe + 24 + optional_size
    magic = struct.unpack_from("<H", data, pe + 24)[0]
    base = struct.unpack_from("<Q", data, pe + 24 + 24)[0] if magic == 0x20B else \
        struct.unpack_from("<I", data, pe + 24 + 28)[0]
    directories = pe + 24 + (112 if magic == 0x20B else 96)
    out = []
    for index in range(count):
        virtual_size, virtual, raw_size, raw = struct.unpack_from("<IIII", data, table + 40 * index + 8)
        flags = struct.unpack_from("<I", data, table + 40 * index + 36)[0]
        out.append((virtual, virtual_size, raw, raw_size, bool(flags & 0x20000000)))
    return base, directories, out


def offset_of(secs, rva):
    for virtual, virtual_size, raw, raw_size, _exec in secs:
        if virtual <= rva < virtual + max(virtual_size, raw_size):
            return raw + (rva - virtual)
    return None


def imports(data, directories, secs):
    """{iat slot rva: 'dll!symbol'} for every imported function."""
    rva, _size = struct.unpack_from("<II", data, directories + 8)
    at = offset_of(secs, rva)
    table = {}
    if at is None:
        return table
    while True:
        original, _stamp, _chain, name_rva, first = struct.unpack_from("<IIIII", data, at)
        if name_rva == 0:
            break
        name_at = offset_of(secs, name_rva)
        end = data.find(b"\0", name_at)
        dll = data[name_at:end].decode("ascii", "replace")
        thunk = offset_of(secs, original or first)
        slot_rva = first        # calls go through the address table, not the name table
        while thunk is not None and thunk + 8 <= len(data):
            value = struct.unpack_from("<Q", data, thunk)[0]
            if value == 0:
                break
            if not value & (1 << 63):
                hint_at = offset_of(secs, value & 0x7FFFFFFF)
                end = data.find(b"\0", hint_at + 2)
                table[slot_rva] = f"{dll}!{data[hint_at + 2:end].decode('ascii', 'replace')}"
            thunk += 8
            slot_rva += 8
        at += 20
    return table


def calls(data, secs, table):
    """[(image rva, 'dll!symbol')] for every call/jmp through the import table."""
    out = []
    for virtual, virtual_size, raw, raw_size, executable in secs:
        if not executable:
            continue
        body = data[raw:raw + raw_size]
        for at in range(len(body) - 6):
            if body[at] != 0xFF or body[at + 1] not in (0x15, 0x25):
                continue
            delta = struct.unpack_from("<i", body, at + 2)[0]
            target = virtual + at + 6 + delta
            name = table.get(target)
            if name:
                out.append((virtual + at, name))
    out.sort()
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("exe", type=Path)
    parser.add_argument("--at", type=lambda v: int(v, 0), help="image RVA to look before")
    parser.add_argument("--window", type=lambda v: int(v, 0), default=0x2000)
    parser.add_argument("--symbol", help="only calls to this symbol name")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    data = args.exe.read_bytes()
    base, directories, secs = sections(data)
    table = imports(data, directories, secs)
    found = calls(data, secs, table)
    print(f"{len(table)} imported functions, {len(found)} call sites through the table")

    if args.symbol:
        wanted = args.symbol.lower()
        hits = [item for item in found if wanted in item[1].lower()]
        print(f"{len(hits)} site(s) calling {args.symbol}")
        for rva, name in hits[:args.limit]:
            print(f"  {base + rva:#012x} ({rva:#x})  {name}")
        return 0

    if args.at is None:
        parser.print_help()
        return 1
    near = [item for item in found if args.at - args.window <= item[0] <= args.at]
    print(f"{len(near)} call(s) through the table in the {args.window:#x} bytes before "
          f"{args.at:#x}, nearest last")
    for rva, name in near[-args.limit:]:
        print(f"  {rva:#x}  +{args.at - rva:#x} before  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
