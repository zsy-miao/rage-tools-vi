"""Unit tests for the extraction tools, on synthetic fixtures.

These do not need the archives: each builds the smallest buffer that exercises one
rule, so a regression in a size law or a framing rule fails here instead of after a
twenty-minute scan.

    python3 tests/test_extraction_tools.py
"""

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

FAILED = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILED.append(name)


def adat_bank(flags, count, records_per_stream=4, data_bytes=64):
    """A minimal well-formed bank the indexer should accept."""
    table_at = 0x50 if flags == 0xFF21 else 0x10 + 4 * count
    header_size = table_at + 8 * records_per_stream * count
    # real containers are 0x800-aligned, and the indexer rounds the extent up
    size = (header_size + data_bytes + 0x7FF) // 0x800 * 0x800
    blob = bytearray(size)
    blob[:4] = b"ADAT"
    struct.pack_into("<HHII", blob, 4, 1, flags, count, header_size)
    kinds = [0x36, 0x55, 0x76, 0xA3]
    for index in range(count * records_per_stream):
        kind = kinds[index % records_per_stream]
        offset = header_size
        record = (kind << 56) | (data_bytes << 28) | offset
        struct.pack_into("<Q", blob, table_at + 8 * index, record)
    return bytes(blob)


def main():
    print("name hash")
    from name_hash_game import murmur3_x64_128, substitute
    first, second = murmur3_x64_128(substitute(b"trailers"))
    check("murmur3 x64-128 of 'trailers' matches the engine value",
          first == 0xFE29572E616C25AD, hex(first))
    check("substitution folds case and separators",
          substitute(b"A\\B.DDS") == b"a/b.dds", substitute(b"A\\B.DDS"))
    check("hash is stable across calls",
          murmur3_x64_128(substitute(b"graphics")) ==
          murmur3_x64_128(substitute(b"graphics")))

    print("adat index")
    from adat_index import extent_bank
    from pathlib import Path as _Path
    import tempfile
    for flags in (0xFF21, 0xFF02):
        blob = adat_bank(flags, 3)
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            handle.write(blob)
            path = _Path(handle.name)
        with path.open("rb") as source:
            end, count, error = extent_bank(source, 0, 1 << 20)
        check(f"0x{flags:04x} bank parses", error is None, error)
        check(f"0x{flags:04x} extent reaches the data end",
              end == len(blob), f"{end} vs {len(blob)}")
        check(f"0x{flags:04x} stream count", count == 3, count)
        path.unlink()

    bad = bytearray(adat_bank(0xFF21, 2))
    bad[0:4] = b"XXXX"
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        handle.write(bytes(bad))
        path = _Path(handle.name)
    with path.open("rb") as source:
        end, _count, error = extent_bank(source, 0, 1 << 20)
    check("a bank without the magic is rejected", end is None and error == "no magic", error)
    path.unlink()

    print("bink index")
    from bink_index import movie_at
    header = bytearray(0x40)
    header[:4] = b"KB2n"
    struct.pack_into("<7I", header, 4, 0x1000, 120, 0x800, 120, 1920, 1080, 30)
    blob = bytes(header) + b"\0" * 0x1000
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        handle.write(blob)
        path = _Path(handle.name)
    with path.open("rb") as source:
        end, fields, error = movie_at(source, 0, len(blob))
    check("a Bink2 header parses", error is None, error)
    check("extent is the aligned payload", end == 0x1000, end)
    check("dimensions are read", (fields["width"], fields["height"]) == (1920, 1080), fields)
    check("the duplicate frame count agrees", fields["frames"] == 120, fields)

    broken = bytearray(blob)
    struct.pack_into("<I", broken, 0x14, 7)          # width 7 is impossible
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        handle.write(bytes(broken))
        path = _Path(handle.name)
    with path.open("rb") as source:
        end, _fields, error = movie_at(source, 0, len(broken))
    check("an implausible width is rejected", end is None, error)
    path.unlink()

    print("coverage union")
    from index_coverage import union
    check("disjoint ranges add up", union([(0, 10, ""), (10, 20, "")]) == 20)
    check("overlap is not double counted", union([(0, 10, ""), (5, 15, "")]) == 15)
    check("contained range is ignored", union([(0, 100, ""), (10, 20, "")]) == 100)

    print("script chain")
    from script_meta import align16, solve_count
    check("align16 rounds up", align16(17) == 32 and align16(16) == 16, align16(17))
    body = bytearray(64)
    body[:4] = b"PSIN"
    # first payload at 16*count + 0x10, then both payloads rounded up to 16
    struct.pack_into(">I", body, 4, 16 * 2 + 0x10 + align16(32) + align16(16))
    struct.pack_into("<II", body, 8, 0xAA, 32)
    struct.pack_into("<II", body, 24, 0xBB, 16)
    solved = solve_count(bytes(body), 0)
    check("a two-descriptor block solves exactly", solved is not None and solved[0] == 2, solved)

    print("ff25 framing")
    from decode_adat_stream import ff25_packets
    blob = bytearray(0x800 * 2)
    for block in range(2):
        base = 0x60 + block * 0x800
        cursor = base
        for _ in range(3):
            packet = b"\xAA" * 4
            struct.pack_into("<H", blob, cursor, len(packet))
            blob[cursor + 2:cursor + 2 + len(packet)] = packet
            cursor += 2 + len(packet)
    packets = ff25_packets(bytes(blob), first=0x60, block=0x800, payload=0x60)
    check("two blocks of three packets are collected", len(packets) == 6, len(packets))
    check("packet payloads survive the walk", packets[0] == b"\xAA" * 4, packets[0])

    print("ff25 phase detection")
    from decode_adat_stream import ff25_auto, ff25_packets_auto

    def phased(phase, blocks=6, per_block=4):
        blob = bytearray(b"\x11" * (0x800 * blocks))
        for block in range(blocks):
            position = block * 0x800 + phase
            for _ in range(per_block):
                packet = b"\x78" + b"\x22" * 40
                struct.pack_into("<H", blob, position, len(packet))
                blob[position + 2:position + 2 + len(packet)] = packet
                position += 2 + len(packet)
        return bytes(blob)

    for phase in (0x60, 0x80, 0xC0, 0x170):
        got, count = ff25_auto(phased(phase))
        check(f"finds the 0x{phase:x} phase", got == phase, f"(got {got:#x})")
        check(f"counts the packets at 0x{phase:x}", count == 24, f"({count})")
    check("returns packet bodies", ff25_packets_auto(phased(0xC0))[0][:1] == b"\x78")

    print("in-place mod")
    from rage import pack_replacement
    import zlib
    packed = pack_replacement(b"MOD_OK", 4430)
    check("a small payload fits the original room", packed is not None)
    check("the replacement is exactly the stored length", len(packed) == 4430, len(packed))
    check("padding does not disturb the stream",
          zlib.decompress(packed) == b"MOD_OK", zlib.decompress(packed))
    packed = pack_replacement(b"x" * 100000, 64)
    check("an oversized payload is refused", packed is None)
    packed = pack_replacement(b"", 8)
    check("an empty payload still fills the room", packed is not None and len(packed) == 8, len(packed))

    print()
    if FAILED:
        print(f"FAIL: {len(FAILED)} check(s) failed: {', '.join(FAILED)}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
