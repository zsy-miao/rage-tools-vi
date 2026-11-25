#!/usr/bin/env python3
"""Compare the last data.rpf child trailer with a known boundary control."""

import argparse
import hashlib
import re
import struct
import zlib
from pathlib import Path

from data_rpf_inventory import psin_valid


LAST_CHILD = 0x1A279000
CONTROL = 0x120D7000
CONTROL_END = 0x121D5C00
TAIL_WINDOW = 0x40000
PSIN_LOOKBACK = 0x100000
CHUNK_BYTES = 0x10000


def read_at(source, offset, size):
    source.seek(offset)
    data = source.read(size)
    if len(data) != size:
        raise ValueError(f"short read at {offset:#x}")
    return data


def read_header(source, start):
    header = read_at(source, start, 0x60)
    if header[:4] != b"9FPR":
        raise ValueError(f"missing RPF9 header at {start:#x}")
    front_end, front_b, trailer_size = struct.unpack_from("<III", header, 4)
    if not 0x60 <= front_b <= front_end or trailer_size == 0 or trailer_size % 16:
        raise ValueError(f"invalid metadata bounds at {start:#x}")
    mode, count, _, version = struct.unpack_from("<IIII", header, 0x20)
    print(f"header {start:#x}: front B {start + front_b:#x}..{start + front_end:#x}, "
          f"trailer size {trailer_size:#x}, count {count}, mode {mode:#010x}/{version:#010x}")
    return trailer_size


def verified_zlib(data, base, decoded_limit=0x40000):
    view = memoryview(data)
    cursor = 0
    for offset in range(-base % 16, len(data) - 1, 16):
        if offset < cursor:
            continue
        cmf, flags = data[offset : offset + 2]
        if cmf & 0x0F != 8 or cmf > 0x78 or ((cmf << 8) | flags) % 31 or flags & 0x20:
            continue
        inflater = zlib.decompressobj()
        try:
            decoded = inflater.decompress(view[offset:], decoded_limit)
        except zlib.error:
            continue
        if inflater.eof:
            cursor = len(data) - len(inflater.unused_data)
            yield base + offset, base + cursor, decoded


def reconstruct_terminal_psin(source, end, raw_start, last_stream_start):
    """Test a CHKS-terminated candidate using adjacent zlib and stored chunks."""
    raw = read_at(source, raw_start, end - raw_start)
    if len(raw) < 20 or raw[-20:-12] != b"CHKS\0\0\0\x14":
        return None
    declared = int.from_bytes(raw[-12:-8], "big")
    decoded_prefix = declared - len(raw)
    needed, remainder = divmod(decoded_prefix, CHUNK_BYTES)
    if not 0 < needed <= 256 or remainder:
        return None
    base = raw_start - PSIN_LOOKBACK
    preceding = read_at(source, base, raw_start - base)
    streams = {
        (stop + 15) & ~15: (start, stop, decoded)
        for start, stop, decoded in verified_zlib(preceding, base)
        if len(decoded) == CHUNK_BYTES and not any(preceding[stop - base : ((stop + 15) & ~15) - base])
    }
    cursor = raw_start
    chunks = []
    while cursor in streams and len(chunks) < needed:
        start, _, decoded = streams[cursor]
        if not chunks and start != last_stream_start:
            return None
        chunks.append(decoded)
        cursor = start
    if len(chunks) != needed:
        return None
    decoded = b"".join(reversed(chunks)) + raw
    if not psin_valid(decoded):
        return None
    print(f"verified PSIN {cursor:#x}..{end:#x}, relative "
          f"{cursor - LAST_CHILD:#x}..{end - LAST_CHILD:#x}, "
          f"{needed} zlib chunks, raw {raw_start:#x}..{end:#x}, decoded {len(decoded):#x}, "
          f"sha256 {hashlib.sha256(decoded).hexdigest()}")
    return cursor


def show_candidate(data, base, size, end, streams):
    start = end - size
    rel = start - base
    if rel < 16:
        return
    trailer = data[rel : end - base]
    longest_zero = max((run.end() - run.start() for run in re.finditer(rb"\0+", trailer)), default=0)
    before = data[rel - 16 : rel]
    leading_pad = len(before) - len(before.rstrip(b"\0"))
    overlapping_streams = sum(a < end and b > start for a, b, _ in streams)
    print(f"{start:#x}..{end:#x}\t"
          f"{start - LAST_CHILD:#x}..{end - LAST_CHILD:#x}\t"
          f"{before.hex()}\t{trailer[:16].hex()}\t{leading_pad}\t"
          f"{longest_zero}\t{overlapping_streams}")


def padding_starts(window, base):
    print("zero runs of 16 bytes or more")
    ends = set()
    for run in re.finditer(rb"\0{16,}", window):
        start, end = base + run.start(), base + run.end()
        print(f"{start:#x}..{end:#x} ({end - start} bytes)")
        aligned = (start + 15) & ~15
        if aligned < end:
            ends.add(aligned)
    return ends


def inspect_endpoints(window, base, trailer_size, decoded_limit=0x40000):
    limit = base + len(window)
    streams = []
    for start, end, decoded in verified_zlib(window, base, decoded_limit):
        streams.append((start, end, len(decoded)))
        tag = ", complete PSIN" if decoded.startswith(b"PSIN") and psin_valid(decoded) else ""
        print(f"verified zlib {start:#x}..{end:#x}, decoded {len(decoded)}, "
              f"first8 {decoded[:8].hex()}{tag}")
    pad_ends = padding_starts(window, base)
    print("archive_trailer\tchild_relative\tbefore16\tfirst16\t"
          "preceding_zero_bytes_(capped_at_16)\tmax_internal_zero_run\t"
          "overlapping_verified_streams")
    for end in sorted(pad_ends | {limit}):
        show_candidate(window, base, trailer_size, end, streams)
    return pad_ends, streams


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("data.rpf"))
    args = parser.parse_args()
    with args.archive.open("rb") as source:
        root_size = read_header(source, 0)
        control_size = read_header(source, CONTROL)
        last_size = read_header(source, LAST_CHILD)
        file_end = source.seek(0, 2)
        root_start = file_end - root_size
        if root_start - TAIL_WINDOW < LAST_CHILD:
            parser.error("archive is too small for this control")
        control_start = CONTROL_END - control_size
        control = read_at(source, control_start - 32, control_size + 64)
        prefix = control[32 : 32 + 16]
        print(f"control trailer {control_start:#x}..{CONTROL_END:#x}, "
              f"child-relative {control_start - CONTROL:#x}..{CONTROL_END - CONTROL:#x}, "
              f"before {control[:32].hex()}, first16 {prefix.hex()}, "
              f"after {control[-32:].hex()}")
        print(f"control trailer sha256 {hashlib.sha256(control[32:-32]).hexdigest()}")

        base = root_start - TAIL_WINDOW
        window = read_at(source, base, TAIL_WINDOW)
        root_prefix = read_at(source, root_start, 16)
        print(f"root trailer {root_start:#x}..{file_end:#x}, first16 {root_prefix.hex()}")
        print(f"terminal window {base:#x}..{root_start:#x}, {len(window):,} bytes")
        for name, block in (("control", prefix), ("root", root_prefix)):
            print(f"{name} trailer first block in terminal window: {window.find(block)}")
        pad_ends, streams = inspect_endpoints(window, base, last_size)
        for end in sorted(pad_ends):
            earlier = [(start, stop) for start, stop, _ in streams if stop <= end]
            if earlier:
                start, stop = earlier[-1]
                raw_start = (stop + 15) & ~15
                if raw_start <= end:
                    psin_start = reconstruct_terminal_psin(source, end, raw_start, start)
                    if psin_start is not None and root_start - end < last_size:
                        print(f"only {root_start - end:#x} bytes from PSIN end to root trailer; "
                              f"child trailer needs {last_size:#x}")
                        print(f"child end upper bound if trailer is contiguous: {psin_start:#x} "
                              f"(child-relative {psin_start - LAST_CHILD:#x})")
                        before = psin_start - PSIN_LOOKBACK
                        print(f"preceding window {before:#x}..{psin_start:#x}")
                        inspect_endpoints(
                            read_at(source, before, PSIN_LOOKBACK), before, last_size, 0x1000000
                        )


if __name__ == "__main__":
    main()
