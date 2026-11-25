"""Decode native UI textures: linear top mip first, then candidate block tiles."""

import argparse
import csv
from pathlib import Path
import struct
import zlib

FORMAT_STRIDES = {0x47: 8, 0x4D: 16, 0x62: 16}


def rgb565(value):
    red = ((value >> 11) & 0x1F) * 255 // 31
    green = ((value >> 5) & 0x3F) * 255 // 63
    blue = (value & 0x1F) * 255 // 31
    return red, green, blue


def decode_bc1(block):
    c0, c1, bits = struct.unpack("<HHI", block)
    a, b = rgb565(c0), rgb565(c1)
    if c0 > c1:
        colors = [a, b, tuple((2 * x + y) // 3 for x, y in zip(a, b)), tuple((x + 2 * y) // 3 for x, y in zip(a, b))]
        alpha = [255] * 4
    else:
        colors = [a, b, tuple((x + y) // 2 for x, y in zip(a, b)), (0, 0, 0)]
        alpha = [255, 255, 255, 0]
    pixels = []
    for index in range(16):
        choice = (bits >> (2 * index)) & 3
        pixels.append((*colors[choice], alpha[choice]))
    return pixels


def decode_bc3(block):
    a0, a1 = block[0], block[1]
    bits = int.from_bytes(block[2:8], "little")
    if a0 > a1:
        alphas = [a0, a1] + [((7 - index) * a0 + index * a1) // 7 for index in range(1, 7)]
    else:
        alphas = [a0, a1] + [((5 - index) * a0 + index * a1) // 5 for index in range(1, 5)] + [0, 255]
    alpha = [alphas[(bits >> (3 * index)) & 7] for index in range(16)]
    c0, c1, color_bits = struct.unpack_from("<HHI", block, 8)
    x, y = rgb565(c0), rgb565(c1)
    colors = [x, y, tuple((2 * p + q) // 3 for p, q in zip(x, y)), tuple((p + 2 * q) // 3 for p, q in zip(x, y))]
    pixels = []
    for index in range(16):
        choice = (color_bits >> (2 * index)) & 3
        pixels.append((*colors[choice], alpha[index]))
    return pixels


def write_png(path, width, height, rgba):
    rows = b"".join(
        b"\x00" + rgba[y * width * 4 : (y + 1) * width * 4] for y in range(height)
    )

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(rows, 9))
    png += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def block_source_index(block_x, block_y, blocks_x, blocks_y, tile):
    if tile == 1:
        return block_y * blocks_x + block_x
    tiles_x = (blocks_x + tile - 1) // tile
    tile_x, inner_x = divmod(block_x, tile)
    tile_y, inner_y = divmod(block_y, tile)
    return ((tile_y * tiles_x + tile_x) * tile + inner_y) * tile + inner_x


def decode(data, width, height, format_code, tile):
    stride = FORMAT_STRIDES[format_code]
    blocks_x, blocks_y = width // 4, height // 4
    top_blocks = blocks_x * blocks_y
    raw = data[: top_blocks * stride]
    rgba = bytearray(width * height * 4)
    for block_y in range(blocks_y):
        for block_x in range(blocks_x):
            source = block_source_index(block_x, block_y, blocks_x, blocks_y, tile)
            block = raw[source * stride : (source + 1) * stride]
            pixels = decode_bc1(block) if stride == 8 else decode_bc3(block)
            for inner_y in range(4):
                for inner_x in range(4):
                    pixel = pixels[inner_y * 4 + inner_x]
                    offset = ((block_y * 4 + inner_y) * width + block_x * 4 + inner_x) * 4
                    rgba[offset : offset + 4] = bytes(pixel)
    return bytes(rgba)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("output/data.rpf/textures-expanded/manifest.tsv"))
    parser.add_argument("--name", required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("output/textures-verify"))
    parser.add_argument("--tiles", type=int, nargs="+", default=[1, 2, 4, 8, 16])
    parser.add_argument("--offset", type=lambda value: int(value, 0), default=0)
    args = parser.parse_args()

    rows = list(csv.DictReader(args.manifest.open(), delimiter="\t"))
    row = next((item for item in rows if item["name"] == args.name), None)
    if row is None:
        raise SystemExit(f"texture not found: {args.name}")
    format_code = int(row["format_code"], 16)
    if format_code not in FORMAT_STRIDES:
        raise SystemExit(f"unsupported format: 0x{format_code:02x}")
    width, height = int(row["width"]), int(row["height"])
    source = args.manifest.parent / "files" / row["file"]
    data = source.read_bytes()
    top_size = (width // 4) * (height // 4) * FORMAT_STRIDES[format_code]
    print(
        f"{args.name}: {width}x{height} format=0x{format_code:02x} "
        f"file={len(data)} top_mip={top_size} source={source}"
    )
    payload = data[args.offset :]
    for tile in args.tiles:
        if tile > min(width // 4, height // 4):
            continue
        rgba = decode(payload, width, height, format_code, tile)
        output = args.out_dir / f"{args.name}-off{args.offset:x}-tile{tile}.png"
        write_png(output, width, height, rgba)
        print(f"  tile {tile}: {output}")


if __name__ == "__main__":
    main()
