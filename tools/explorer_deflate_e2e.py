#!/usr/bin/env python3
"""Compare a known raw-DEFLATE control with Python's independent decoder."""
import argparse
from pathlib import Path
import subprocess
import tempfile
import zlib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("data.rpf"))
    parser.add_argument("--binary", type=Path, default=Path("explorer/target/debug/annoyed-extract"))
    parser.add_argument("--index-out", type=Path, help="also write a full-coverage control index")
    args = parser.parse_args()
    start, end = 0x966000, 0x966308
    with args.archive.open("rb") as source:
        source.seek(start)
        stored = source.read(end - start)
    decoder = zlib.decompressobj(-zlib.MAX_WBITS)
    expected = decoder.decompress(stored) + decoder.flush()
    assert decoder.eof and not decoder.unused_data and len(expected) == 1318
    assert expected.startswith(b"RBF0")
    if args.index_out:
        size = args.archive.stat().st_size
        with args.index_out.open("x", encoding="utf-8") as index:
            index.write("kind\tstart\tend\tstored_bytes\tdecoded_bytes\tchain_start\n")
            index.write(f"unclassified\t0x0\t{start:#x}\t{start}\t\t\n")
            index.write(f"raw_deflate\t{start:#x}\t{end:#x}\t{end-start}\t{len(expected)}\t{start:#x}\n")
            index.write(f"unclassified\t{end:#x}\t{size:#x}\t{size-end}\t\t\n")
    with tempfile.TemporaryDirectory(prefix="annoyed-deflate-") as directory:
        output = Path(directory) / "payload.bin"
        subprocess.run([str(args.binary), "deflate", str(args.archive), hex(start), hex(end), str(output)], check=True)
        assert output.read_bytes() == expected
    print("raw DEFLATE control matches independent decoder; format has no checksum")


if __name__ == "__main__":
    main()
