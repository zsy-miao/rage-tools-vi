"""Correct PE section mapping + pattern scans, so negatives can be trusted.

The order of the four dwords after a section name is
`VirtualSize, VirtualAddress, SizeOfRawData, PointerToRawData`.  Several earlier
ad-hoc scans in this repository unpacked them in a different order and therefore
searched the wrong byte range while claiming to search `.text`.  This tool exists
so that "not found in .text" means what it says.

  python3 tools/pe_scan.py sections
  python3 tools/pe_scan.py magic PSIN LSNS 9FPR RSC7 ADAT
  python3 tools/pe_scan.py immediate 0x67452301 0xEFCDAB89
  python3 tools/pe_scan.py sbox
  python3 tools/pe_scan.py rotate
"""

import argparse
import struct
import sys
from pathlib import Path

EXE = Path("cache/exe/game_scarlett_master.exe")


class PE:
    def __init__(self, path=EXE):
        self.data = Path(path).read_bytes()
        d = self.data
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        self.image_base = struct.unpack_from("<Q", d, pe + 48)[0]
        nsec = struct.unpack_from("<H", d, pe + 6)[0]
        opt_size = struct.unpack_from("<H", d, pe + 20)[0]
        table = pe + 24 + opt_size
        self.sections = []
        for index in range(nsec):
            off = table + 40 * index
            name = d[off:off + 8].rstrip(b"\0").decode(errors="replace")
            vsize, vaddr, raw_size, raw_ptr = struct.unpack_from("<IIII", d, off + 8)
            self.sections.append({
                "name": name,
                "vaddr": self.image_base + vaddr,
                "vsize": vsize,
                "raw_ptr": raw_ptr,
                "raw_size": raw_size,
            })

    def section(self, name):
        for sect in self.sections:
            if sect["name"] == name:
                return sect
        raise KeyError(name)

    def blob(self, name):
        sect = self.section(name)
        return self.data[sect["raw_ptr"]:sect["raw_ptr"] + sect["raw_size"]]

    def foff(self, va):
        rva = va - self.image_base
        for sect in self.sections:
            if sect["vaddr"] - self.image_base <= rva < sect["vaddr"] - self.image_base + max(
                    sect["vsize"], sect["raw_size"]):
                return sect["raw_ptr"] + (rva - (sect["vaddr"] - self.image_base))
        return None

    def va(self, foff):
        for sect in self.sections:
            if sect["raw_ptr"] <= foff < sect["raw_ptr"] + sect["raw_size"]:
                return sect["vaddr"] + (foff - sect["raw_ptr"])
        return None


def cmd_sections(pe, _args):
    print(f"image base {pe.image_base:#x}")
    for sect in pe.sections:
        end = sect["vaddr"] + max(sect["vsize"], sect["raw_size"])
        print(f"{sect['name']:10s} {sect['vaddr']:#12x} vsize {sect['vsize']:#10x} "
              f"raw {sect['raw_ptr']:#10x}+{sect['raw_size']:#x}  ..{end:#x}")


def cmd_magic(pe, args):
    for text in args:
        needle = text.encode()
        hits = []
        start = 0
        while True:
            index = pe.data.find(needle, start)
            if index < 0:
                break
            hits.append(index)
            start = index + 1
        print(f"{text!r}: {len(hits)} byte occurrences")
        for index in hits[:12]:
            print(f"   file {index:#x}  va {pe.va(index) if pe.va(index) else 0:#x}")


def cmd_immediate(pe, args):
    blob = pe.blob(".text")
    base = pe.section(".text")["vaddr"]
    for text in args:
        value = int(text, 0)
        packed = struct.pack("<I", value & 0xFFFFFFFF)
        hits = []
        start = 0
        while True:
            index = blob.find(packed, start)
            if index < 0:
                break
            hits.append(index)
            start = index + 1
        print(f"u32 {value:#010x}: {len(hits)} in .text")
        for index in hits[:8]:
            print(f"   va {base + index:#x}")


def cmd_sbox(pe, _args):
    """AES forward and inverse S-box first rows, as byte strings."""
    forward = bytes.fromhex("637c777bf26b6fc53001672bfed7ab76")
    inverse = bytes.fromhex("52096ad53036a538bf40a39e81f3d7fb")
    for label, needle in (("AES forward", forward), ("AES inverse", inverse)):
        hits = []
        start = 0
        while True:
            index = pe.data.find(needle, start)
            if index < 0:
                break
            hits.append(index)
            start = index + 1
        print(f"{label} sbox: {len(hits)} occurrences")
        for index in hits[:8]:
            print(f"   file {index:#x}  va {pe.va(index) if pe.va(index) else 0:#x}")


def cmd_rotate(pe, _args):
    blob = pe.blob(".text")
    base = pe.section(".text")["vaddr"]
    hits = [i for i in range(len(blob) - 3)
            if blob[i] == 0x48 and blob[i + 1] == 0xC1 and (blob[i + 2] & 0x38) in (0, 8)]
    buckets = {}
    for index in hits:
        key = index // 256
        buckets[key] = buckets.get(key, 0) + 1
    top = sorted(buckets.items(), key=lambda item: -item[1])[:10]
    print(f"rotate instructions in .text: {len(hits)} over {len(blob)} bytes")
    for key, count in top:
        print(f"   {count:3d} in 256 B at va {base + key * 256:#x}")


COMMANDS = {
    "sections": cmd_sections,
    "magic": cmd_magic,
    "immediate": cmd_immediate,
    "sbox": cmd_sbox,
    "rotate": cmd_rotate,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("args", nargs="*")
    parser.add_argument("--exe", type=Path, default=EXE)
    args = parser.parse_args()
    pe = PE(args.exe)
    COMMANDS[args.command](pe, args.args)


if __name__ == "__main__":
    main()
