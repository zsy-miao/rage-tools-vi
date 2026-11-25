"""Patch a guard `int3` in a copy of the image, and run the copy.

The image stops at `swi(3)` sites that follow a failed initialisation call. Each stop names
what the platform was expected to provide. Patching that one byte to `nop` in a **copy**
turns the stop into a log line, so the next expectation appears instead of the same abort.

The original is never touched: the tool writes `<name>.patched.exe` beside a copy and the
caller runs that copy.

    python3 tools/patch_guard.py --exe cache/exe/game_scarlett_master.exe --at 0x2237178
    python3 tools/patch_guard.py --exe ... --at 0x2237178,0x55a91c21 --out cache/patched.exe
"""

import argparse
import struct
import sys
from pathlib import Path

TEXT_RVA = 0x1000
TEXT_RAW = 0x400


def rva_to_offset(data, rva):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    size = struct.unpack_from("<H", data, pe + 20)[0]
    table = pe + 24 + size
    for index in range(count):
        virtual_size, virtual, raw_size, raw = struct.unpack_from("<IIII", data, table + 40 * index + 8)
        if virtual <= rva < virtual + max(virtual_size, raw_size):
            return raw + (rva - virtual)
    raise ValueError(f"RVA {rva:#x} is not inside any section")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--at", required=True, help="image RVA(s), comma separated")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--byte", type=lambda v: int(v, 0), default=0x90,
                        help="replacement byte (default 0x90, a nop)")
    parser.add_argument("--jump", type=int, default=0,
                        help="replace N bytes starting at --at with a short jump over them")
    parser.add_argument("--input", type=Path,
                        help="start from an already patched image instead of --exe")
    args = parser.parse_args()

    source = args.input or args.exe
    data = bytearray(source.read_bytes())
    for token in args.at.split(","):
        rva = int(token, 0)
        offset = rva_to_offset(data, rva)
        if args.jump:
            if not 2 <= args.jump <= 127:
                raise SystemExit("--jump must be 2..127 bytes")
            data[offset] = 0xEB
            data[offset + 1] = args.jump - 2
            for index in range(2, args.jump):
                data[offset + index] = 0x90
            print(f"{rva:#x} -> file {offset:#x}: jump over {args.jump} bytes")
            continue
        before = data[offset]
        data[offset] = args.byte
        print(f"{rva:#x} -> file {offset:#x}: {before:#04x} -> {data[offset]:#04x}")
        if before != 0xCC:
            print("  warning: the byte there was not 0xCC")
    out = args.out or args.exe.with_name(args.exe.stem + ".patched.exe")
    out.write_bytes(data)
    print(f"wrote {out} ({len(data):,} B)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
