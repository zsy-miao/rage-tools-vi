#!/usr/bin/env python3
"""Recover one descriptor-backed texture control from a bounded source window."""

import argparse
from collections import Counter
from functools import cache
from hashlib import sha256
from itertools import permutations
from pathlib import Path
import struct
import zlib

from native_texture_scan import texture_dictionary, virtual_offset
from texture_decode import block_source_index, decode, decode_bc3, write_png


MAX_WINDOW = 0x800000
MAX_STREAM = 0x400000


def aligned(offset):
    return (offset + 15) & ~15


def stream_at(window, start):
    decoder = zlib.decompressobj()
    decoded = decoder.decompress(window[start:], MAX_STREAM + 1)
    if not decoder.eof or len(decoded) > MAX_STREAM:
        raise ValueError("incomplete or oversized zlib stream")
    return decoded, len(window) - len(decoder.unused_data)


def dictionary_count(header):
    if len(header) < 0x3C:
        return 0
    hashes, count, capacity = struct.unpack_from("<QHH", header, 0x20)
    pointers, ptr_count, ptr_capacity = struct.unpack_from("<QHH", header, 0x30)
    if 0 < count == capacity == ptr_count == ptr_capacity and hashes >> 28 == pointers >> 28 == 5:
        return count
    return 0


def graphics_end(system, count):
    pointer_array = struct.unpack_from("<Q", system, 0x30)[0]
    offset = virtual_offset(pointer_array, 0x50000000, len(system), count * 8)
    end = 0
    for (pointer,) in struct.iter_unpack("<Q", system[offset : offset + count * 8]):
        descriptor = virtual_offset(pointer, 0x50000000, len(system), 0x40)
        blocks, stride, _, _, address = struct.unpack_from("<IHHQQ", system, descriptor + 8)
        size = blocks * stride
        start = virtual_offset(address, 0x60000000, MAX_WINDOW, size)
        end = max(end, start + size)
    return end


def find_control(window, base, code, name, min_mips):
    header_hits = valid_dictionaries = 0
    for start in range(0, len(window) - 1, 16):
        cmf, flg = window[start : start + 2]
        if cmf != 0x78 or ((cmf << 8) | flg) % 31 or flg & 0x20:
            continue
        try:
            header = zlib.decompressobj().decompress(window[start:], 0x3C)
            count = dictionary_count(header)
            if not count:
                continue
            header_hits += 1
            system, end = stream_at(window, start)
            ranges = [(base + start, base + end)]
            required = graphics_end(system, count)
            graphics = bytearray()
            while len(graphics) < required:
                next_start = aligned(end)
                if next_start >= len(window) or any(window[end:next_start]):
                    raise ValueError("missing adjacent graphics stream")
                chunk, end = stream_at(window, next_start)
                graphics.extend(chunk)
                ranges.append((base + next_start, base + end))
            records = texture_dictionary(system, graphics)
        except (zlib.error, ValueError):
            continue
        valid_dictionaries += 1
        candidates = [row for row in records if row[5] == code
                      and (name is None or row[0] == name) and system[row[2] + 0x3E] >= min_mips]
        if candidates:
            selected = min(candidates, key=lambda row: row[-1])
            return selected, system, graphics, ranges, count
    raise ValueError(f"no matching descriptor-backed texture among {header_hits} dictionary "
                     f"headers and {valid_dictionaries} valid dictionaries in the window")


def morton(x, y, tile):
    value = 0
    for bit in range(tile.bit_length() - 1):
        value |= ((x >> bit) & 1) << (2 * bit)
        value |= ((y >> bit) & 1) << (2 * bit + 1)
    return value


def reordered_blocks(data, indices):
    return b"".join(data[index * 16:(index + 1) * 16] for index in indices)


def top_orders(data, width, height):
    blocks_x, blocks_y = width // 4, height // 4
    seen = set()
    for tile in (1, 2, 4, 8, 16):
        if blocks_x % tile or blocks_y % tile:
            continue
        for order in ("row", "morton") if tile > 1 else ("row",):
            indices = []
            for y in range(blocks_y):
                for x in range(blocks_x):
                    index = block_source_index(x, y, blocks_x, blocks_y, tile)
                    if order == "morton":
                        inner_x, inner_y = x % tile, y % tile
                        index += morton(inner_x, inner_y, tile) - inner_y * tile - inner_x
                    indices.append(index)
            signature = tuple(indices)
            if signature in seen:
                continue
            seen.add(signature)
            yield f"{order}{tile}", reordered_blocks(data, indices)


def seam_score(rgba, width, height, step=4):
    pixels = [(r * a // 255, g * a // 255, b * a // 255, a)
              for r, g, b, a in struct.iter_unpack("4B", rgba)]
    total = samples = 0
    for y in range(height):
        for x in range(width):
            index = y * width + x
            neighbors = []
            if x and x % step == 0:
                neighbors.append(index - 1)
            if y and y % step == 0:
                neighbors.append(index - width)
            for neighbor in neighbors:
                total += sum(abs(a - b) for a, b in zip(pixels[index], pixels[neighbor]))
                samples += 4
    if not samples:
        raise ValueError("control needs an interior block boundary")
    return total / samples


def deposit(value, mask):
    result = 0
    while mask and value:
        bit = mask & -mask
        if value & 1:
            result |= bit
        mask ^= bit
        value >>= 1
    return result


def standard_128bpp_indices():
    # Microsoft's published 2D 128-bpp standard swizzle treats x as bytes.
    # These offsets address the first 4 KiB within the reference pattern.
    return tuple(
        (deposit(16 * x, 0xAACF) | deposit(y, 0x5530)) >> 4
        for y in range(16) for x in range(16)
    )


def search_address_bits(data):
    edges = []
    for offset in range(0, len(data), 16):
        pixels = [(r * a // 255, g * a // 255, b * a // 255, a)
                  for r, g, b, a in decode_bc3(data[offset:offset + 16])]
        edges.append((pixels[3::4], pixels[::4], pixels[12:], pixels[:4]))
    # During x+1 or y+1, a carry flips the lower set bits and one clear bit.
    # The sum for this transition depends on those physical bits, independent
    # of the remaining address assignments.
    @cache
    def carry_cost(axis, lower, high):
        mask = lower | high
        left, right = axis * 2, axis * 2 + 1
        return sum(
            abs(a - b)
            for index in range(256) if index & mask == lower
            for lhs, rhs in zip(edges[index][left], edges[index ^ mask][right])
            for a, b in zip(lhs, rhs)
        )

    @cache
    def axis_cost(axis, bits):
        lower = total = 0
        for bit in bits:
            high = 1 << bit
            total += carry_cost(axis, lower, high)
            lower |= high
        return total

    ranked = sorted(
        (axis_cost(0, bits[:4]) + axis_cost(1, bits[4:]), bits)
        for bits in permutations(range(8))
    )
    samples = 2 * 15 * 16 * 4 * 4
    for total, bits in ranked[:5]:
        print(f"BC3 address bits x={bits[:4]} y={bits[4:]}: seam delta {total / samples:.4f}")
    total, bits = ranked[0]
    indices = tuple(
        sum(((coord >> bit) & 1) << physical
            for coord, mapping in ((x, bits[:4]), (y, bits[4:]))
            for bit, physical in enumerate(mapping))
        for y in range(16) for x in range(16)
    )
    return total / samples, indices


def decode_control(data, width, height, code, mips, output, address_bits):
    if code != 0x4D or mips != 1 or width % 4 or height % 4 or len(data) != width * height:
        raise ValueError("PNG probe expects a single 0x4d mip with an exact BC3 block budget")
    results = []
    for order, blocks in top_orders(data, width, height):
        rgba = decode(blocks, width, height, code, 1)
        results.append((seam_score(rgba, width, height), order, rgba))
    results.sort()
    for score, order, _ in results:
        print(f"BC3 {order}: mean premultiplied RGBA seam delta {score:.4f}")
    score, order, rgba = results[0]
    if address_bits:
        if (width, height) != (64, 64):
            raise ValueError("address-bit comparison expects a 16×16 grid of BC3 blocks")
        bit_score, indices = search_address_bits(data)
        bit_pixels = decode(reordered_blocks(data, indices), width, height, code, 1)
        if bit_score != seam_score(bit_pixels, width, height):
            raise ValueError("address-bit score disagrees with decoded pixels")
        if indices == standard_128bpp_indices():
            print("all 256 block addresses match the published 128-bpp standard-swizzle prefix")
        if bit_score < score:
            score, order, rgba = bit_score, "address bits", bit_pixels
    write_png(output, width, height, rgba)
    print(f"lowest seam delta {score:.4f}, {order}: {output}")


def paged_indices(blocks_x, blocks_y, page_order):
    pitch = (blocks_x + 15) // 16
    inner = standard_128bpp_indices()
    return tuple(
        256 * page_order[(y // 16) * pitch + x // 16] + inner[(y % 16) * 16 + x % 16]
        for y in range(blocks_y) for x in range(blocks_x)
    )


def decode_bc7_control(data, width, height, mips, output):
    try:
        from PIL import Image
    except ImportError as error:
        raise ValueError("the BC7 probe needs Pillow's BC7 decoder") from error
    if mips != 1 or width % 4 or height % 4:
        raise ValueError("BC7 probe expects one mip with dimensions divisible by four")
    blocks_x, blocks_y = width // 4, height // 4
    pages_x, pages_y = (blocks_x + 15) // 16, (blocks_y + 15) // 16
    if len(data) != pages_x * pages_y * 0x1000:
        raise ValueError("BC7 buffer size does not match the padded 4 KiB page grid")
    print(f"BC7 grid: {blocks_x}×{blocks_y} active blocks, {pages_x}×{pages_y} 4 KiB pages")

    pages = [(x, y) for y in range(pages_y) for x in range(pages_x)]
    tile = 1 << (max(pages_x, pages_y) - 1).bit_length()
    positions = {coord: index for index, coord in
                 enumerate(sorted(pages, key=lambda point: morton(*point, tile)))}
    orders = {
        "linear tight": range(blocks_x * blocks_y),
        "linear padded": tuple(y * pages_x * 16 + x for y in range(blocks_y) for x in range(blocks_x)),
        "row-major pages": paged_indices(blocks_x, blocks_y, range(len(pages))),
        "column-major pages": paged_indices(blocks_x, blocks_y, [x * pages_y + y for x, y in pages]),
        "compact Morton pages": paged_indices(blocks_x, blocks_y, [positions[coord] for coord in pages]),
    }
    results = []
    for name, indices in orders.items():
        blocks = reordered_blocks(data, indices)
        rgba = Image.frombytes("RGBA", (width, height), blocks, "bcn", (7, "BC7")).tobytes()
        score = seam_score(rgba, width, height)
        outer = ""
        if max(width, height) > 64:
            outer = f", page seam {seam_score(rgba, width, height, 64):.4f}"
        print(f"BC7 {name}: seam delta {score:.4f}{outer}")
        results.append((score, name, rgba, indices))
    score, name, rgba, indices = min(results)

    active = set(indices)
    modes = Counter()
    pad_zero = 0
    for index, offset in enumerate(range(0, len(data), 16)):
        block = data[offset:offset + 16]
        if index in active:
            mode = (block[0] & -block[0]).bit_length() - 1
            modes[mode] += 1
        else:
            pad_zero += not any(block)
    print(f"active BC7 modes {dict(sorted(modes.items()))} (-1 = reserved), "
          f"zero padding blocks {pad_zero}/{len(data) // 16 - len(active)}")
    write_png(output, width, height, rgba)
    print(f"lowest seam delta {score:.4f}, {name}: {output}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("textures.rpf"))
    parser.add_argument("--start", type=lambda value: int(value, 0), default=0x9160010)
    parser.add_argument("--bytes", type=lambda value: int(value, 0), default=0x1000)
    parser.add_argument("--format", type=lambda value: int(value, 0), choices=(0x4D, 0x62), default=0x4D)
    parser.add_argument("--name")
    parser.add_argument("--min-mips", type=int, default=1)
    parser.add_argument("--png-out", type=Path)
    parser.add_argument("--address-bits", action="store_true",
                        help="also compare all 8! address-bit permutations on a 64×64 BC3 control")
    args = parser.parse_args()
    if args.start < 0 or args.start % 16 or not 0 < args.bytes <= MAX_WINDOW:
        parser.error("start must be nonnegative and 16-byte aligned; window must be 1 byte to 8 MiB")
    if not 1 <= args.min_mips <= 16:
        parser.error("--min-mips must be between 1 and 16")
    if args.address_bits and (args.format != 0x4D or args.png_out is None):
        parser.error("--address-bits requires --format 0x4d and --png-out")
    with args.archive.open("rb") as source:
        source.seek(args.start)
        window = memoryview(source.read(args.bytes))
    print(f"source {args.archive}, window {args.start:#x}..{args.start + len(window):#x}")
    try:
        selected, system, graphics, ranges, count = find_control(
            window, args.start, args.format, args.name, args.min_mips
        )
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    name, name_hash, descriptor, width, height, code, offset, size = selected
    data = graphics[offset : offset + size]
    print("stored zlib ranges " + ", ".join(f"{start:#x}..{end:#x}" for start, end in ranges))
    print(f"validated dictionary textures {count}, system bytes {len(system):#x}")
    print(f"{name} ({name_hash:#010x}), {width}x{height}, format {code:#x}, "
          f"{system[descriptor + 0x3E]} mips, graphics {offset:#x}..{offset + size:#x}, "
          f"SHA-256 {sha256(data).hexdigest()}")
    print(f"system descriptor {descriptor:#x}..{descriptor + 0x60:#x}")
    for pos in range(0, 0x60, 16):
        print(f"  +{pos:02x} {system[descriptor + pos:descriptor + pos + 16].hex(' ')}")
    if args.png_out:
        try:
            mips = system[descriptor + 0x3E]
            if code == 0x62:
                decode_bc7_control(data, width, height, mips, args.png_out)
            else:
                decode_control(data, width, height, code, mips, args.png_out, args.address_bits)
        except ValueError as error:
            parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
