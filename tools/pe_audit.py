"""Static audit of a PE image — no execution, no network.

Written for the GTA VI executable: what it is, whether it looks packed, who signed
it, and whether it holds the strings this project needs (RPF9 container handling,
cipher material, script container tags).

    python3 tools/pe_audit.py FILE [--strings 40]
"""
import argparse
import hashlib
import math
import struct
from collections import Counter
from pathlib import Path

MACHINES = {0x8664: "x86-64", 0x14C: "x86", 0xAA64: "ARM64"}
INTEREST = [b"RPF9", b"8FPR", b"PSIN", b"LSCH", b"LSNS", b"ADAT", b"AES",
            b"aes", b"EXEC", b"opcode", b"jhash", b"joaat", b"CRC", b"ooo",
            b"oo2core", b"Oodle", b"Bink", b"d3d12", b"xor", b"key"]


def sections(data, pe):
    count = struct.unpack_from("<H", data, pe + 6)[0]
    size = struct.unpack_from("<H", data, pe + 20)[0]
    base = pe + 24 + size
    out = []
    for i in range(count):
        off = base + 40 * i
        name = data[off:off + 8].rstrip(b"\0").decode(errors="replace")
        vsize, vaddr, rsize, rptr = struct.unpack_from("<IIII", data, off + 8)
        out.append((name, vaddr, vsize, rptr, rsize))
    return out


def entropy(chunk):
    if not chunk:
        return 0.0
    counts = Counter(chunk)
    n = len(chunk)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", type=Path)
    parser.add_argument("--strings", type=int, default=20)
    args = parser.parse_args()

    data = args.file.read_bytes()
    print(f"file      {args.file.name}")
    print(f"size      {len(data):,} B")
    print(f"sha256    {hashlib.sha256(data).hexdigest()}")
    print(f"md5       {hashlib.md5(data).hexdigest()}")
    if data[:2] != b"MZ":
        print("not a PE image (no MZ)")
        return 1
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        print(f"MZ at 0, but no PE signature at 0x{pe:x}")
        return 1
    machine, nsec, stamp = struct.unpack_from("<HHI", data, pe + 4)
    magic = struct.unpack_from("<H", data, pe + 24)[0]
    print(f"machine   {MACHINES.get(machine, hex(machine))}  sections {nsec}  "
          f"timestamp {stamp}  magic {magic:#x} "
          f"({'PE32+' if magic == 0x20b else 'PE32'})")
    for name, vaddr, vsize, rptr, rsize in sections(data, pe):
        chunk = data[rptr:rptr + rsize]
        print(f"  {name:8s} va {vaddr:#010x} vsize {vsize:>9,} raw {rsize:>9,} "
              f"entropy {entropy(chunk):.2f}")
    hits = {needle: data.count(needle) for needle in INTEREST if data.count(needle)}
    print("strings of interest:", {k.decode(): v for k, v in hits.items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
