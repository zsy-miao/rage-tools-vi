"""Test fixed-stride offset and length hypotheses against small RPF9 controls."""

import argparse
from collections import defaultdict
from itertools import permutations
from pathlib import Path
import struct
import zlib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("archive", type=Path, help="path to a known four-payload RPF9 control")
parser.add_argument(
    "--region", choices=("front-a", "front", "trailer"), action="append",
    help="metadata region to test; repeat to select more than one (default: front and trailer)",
)
parser.add_argument(
    "--stride", type=int, metavar="BYTES", action="append",
    help="record stride to test; repeat to select more than one (default: all fitting strides)",
)
args = parser.parse_args()
if args.stride and min(args.stride) < 4:
    parser.error("--stride must be at least 4 bytes")
archive = args.archive.read_bytes()
if len(archive) < 0x40 or archive[:4] != b"9FPR":
    parser.error("expected an RPF9 control sample")

start, front_table, trailer_bytes = struct.unpack_from('<III', archive, 4)
trailer = len(archive) - trailer_bytes
known_samples = {
    (0x340, 0x310, 0x1570, 0x1600): ((0x340, 0x1000, 0x12a0, 0x13c0), ()),
    (0x330, 0x300, 0x3450, 0x34e0): ((0x1000, 0x3000, 0x31a0, 0x32b0), ((0x1000, 0x2e50),)),
}
sample = known_samples.get((start, front_table, trailer, len(archive)))
if sample is None:
    parser.error("header boundaries do not match a known control sample")
payload_starts, opaque_spans = sample
opaque_ends = dict(opaque_spans)
ranges = []
for offset in payload_starts:
    if offset in opaque_ends:
        ranges.append((offset, opaque_ends[offset], None))
        continue
    inflater = zlib.decompressobj()
    data = inflater.decompress(archive[offset:trailer], 65537)
    if not inflater.eof:
        parser.error(f'expected a complete zlib stream at {offset:#x}')
    ranges.append((offset, trailer - len(inflater.unused_data), len(data)))


def align(size, unit):
    return (size + unit - 1) // unit * unit


variants = {}
for base in (0, start):
    for unit in (1, 2, 4, 8, 16, 32):
        if all((offset - base) % unit == 0 for offset, _, _ in ranges):
            variants['offset', base, unit] = tuple((offset - base) // unit for offset, _, _ in ranges)
lengths = {
    'stored': tuple(end - offset for offset, end, _ in ranges),
    'slot': tuple(
        end - offset
        for offset, end in zip(payload_starts, (*payload_starts[1:], trailer))
    ),
}
decoded_sizes = tuple(decoded for _, _, decoded in ranges)
if all(size is not None for size in decoded_sizes):
    lengths['decoded'] = decoded_sizes

for label, observed in lengths.items():
    for alignment in (1, 16):
        spans = tuple(align(length, alignment) for length in observed)
        for unit in (1, 2, 4, 8, 16):
            if all(span % unit == 0 for span in spans):
                variants[label, alignment, unit] = tuple(span // unit for span in spans)


def signatures(values, mode):
    if mode == 'plain':
        return (tuple(sorted(values)),)
    if mode == 'add':
        smallest = min(values)
        return (tuple(sorted(n - smallest for n in values)),)
    return tuple(sorted(tuple(sorted(n ^ anchor for n in values)) for anchor in values))

tables = {
    'front-a': archive[0x60:front_table],
    'front': archive[front_table:start],
    'trailer': archive[trailer:],
}
for name in dict.fromkeys(args.region or ('front', 'trailer')):
    table = tables[name]
    fitting_strides = range(4, len(table) // 3 + 1)
    strides = sorted(set(args.stride or fitting_strides).intersection(fitting_strides))
    if not strides:
        parser.error(f"none of the requested strides fit four fields in {name}")
    candidates = [dict(), dict(), dict()]
    for width in range(6, 33):
        for mode_id, mode in enumerate(('plain', 'add', 'xor')):
            lookup = defaultdict(list)
            for label, values in variants.items():
                if max(values) < 1 << width:
                    lookup[signatures(values, mode)].append((label, values))
            candidates[mode_id][width] = lookup
    hits = {mode: set() for mode in ('plain', 'add', 'xor')}
    tests = 0
    for order in ('little', 'big'):
        raw = int.from_bytes(table, order)
        bits = len(table) * 8
        for stride_bytes in strides:
            stride = stride_bytes * 8
            for field in range(0, bits - 3 * stride - 5):
                lanes = tuple(raw >> (field + i * stride) for i in range(4))
                for width in range(6, min(32, bits - field - 3 * stride) + 1):
                    mask = (1 << width) - 1
                    values = tuple(n & mask for n in lanes)
                    if len(set(values)) != 4:
                        continue
                    tests += 1
                    for i, mode in enumerate(hits):
                        for label, expected in candidates[i][width].get(signatures(values, mode), ()):
                            for permutation in permutations(range(4)):
                                permuted = tuple(expected[j] for j in permutation)
                                if mode == 'plain':
                                    ok = values == permuted
                                elif mode == 'add':
                                    ok = len({n - m for n, m in zip(values, permuted)}) == 1
                                else:
                                    ok = len({n ^ m for n, m in zip(values, permuted)}) == 1
                                if ok:
                                    hits[mode].add((order, stride_bytes, field, width, label, permutation))
    print(name, 'fields tested:', tests)
    for mode, matches in hits.items():
        offsets = {v for v in matches if v[4][0] == 'offset'}
        sizes = matches - offsets
        offset_rows = {(order, stride, permutation) for order, stride, _, _, _, permutation in offsets}
        size_rows = {(order, stride, permutation) for order, stride, _, _, _, permutation in sizes}
        print(
            f'{mode} offset matches: {len(offsets)} size matches: {len(sizes)} '
            f'compatible same-record pairs: {len(offset_rows & size_rows)}'
        )
        for candidate in sorted(offsets)[:5]:
            print('  offset candidate:', candidate)
