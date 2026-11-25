#!/usr/bin/env python3
"""Create and check a small synthetic PNG-in-zlib RPF fixture."""
import argparse
from pathlib import Path
import struct
import subprocess
import zlib


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--assert-screenshot", type=Path)
    parser.add_argument("--format", choices=("png", "jpeg"), default="png")
    args = parser.parse_args()
    if args.assert_screenshot:
        pixel = subprocess.check_output([
            "ffmpeg", "-loglevel", "error", "-i", str(args.assert_screenshot),
            "-vf", "crop=2:2:830:500", "-frames:v", "1", "-f", "rawvideo",
            "-pix_fmt", "rgb24", "pipe:1",
        ])[:3]
        if len(pixel) != 3 or any(abs(a - b) > 10 for a, b in zip(pixel, (20, 160, 90))):
            raise SystemExit(f"Unexpected preview pixel: {list(pixel)}")
        print(f"preview pixel: {list(pixel)}")
        return
    args.directory.mkdir(parents=True, exist_ok=True)
    width = height = 16
    rows = (b"\0" + bytes((20, 160, 90)) * width) * height
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    payload = png
    if args.format == "jpeg":
        payload = subprocess.check_output([
            "ffmpeg", "-loglevel", "error", "-f", "image2pipe", "-vcodec", "png",
            "-i", "pipe:0", "-frames:v", "1", "-f", "image2pipe", "-vcodec", "mjpeg",
            "-q:v", "2", "pipe:1",
        ], input=png)
    stored = zlib.compress(payload)
    header = bytearray(96)
    header[:4] = b"9FPR"
    struct.pack_into("<I", header, 4, 96)
    with (args.directory / "image.rpf").open("xb") as archive:
        archive.write(header)
        archive.write(stored)
    end = 96 + len(stored)
    with (args.directory / "image.tsv").open("x", encoding="utf-8") as index:
        index.write("kind\tstart\tend\tstored_bytes\tdecoded_bytes\tchain_start\n")
        index.write("front\t0x0\t0x60\t96\t\t\n")
        index.write(f"zlib\t0x60\t0x{end:x}\t{len(stored)}\t{len(payload)}\t0x60\n")


if __name__ == "__main__":
    main()
