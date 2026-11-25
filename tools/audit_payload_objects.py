"""Independently validate payload objects using the local RPF9 controls."""

import argparse
from bisect import bisect_right
from collections import defaultdict
import csv
from pathlib import Path
import struct
import subprocess
import xml.etree.ElementTree as ET
import zlib

CHUNK_SIZE = 65536


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_map(binary, path, data, bounds=None):
    args = [str(binary), 'map', str(path)]
    if bounds:
        args.extend(f'{offset:x}' for offset in bounds)
    output = subprocess.check_output(args, text=True)
    rows = list(csv.DictReader(output.splitlines(), delimiter='\t'))
    cursor, end = bounds if bounds else (0, len(data))
    by_chain = defaultdict(list)
    for row in rows:
        start = int(row['start'], 16)
        stop = int(row['end'], 16)
        require(start == cursor and start < stop <= end, 'range map does not partition the pack')
        cursor = stop
        if row['kind'] == 'zero_run':
            require(not any(data[start:stop]), f'nonzero bytes in zero run at {start:#x}')
        if row['kind'] != 'zlib':
            continue
        decoder = zlib.decompressobj()
        decoded = decoder.decompress(data[start:stop])
        require(decoder.eof and not decoder.unused_data, f'invalid zlib stream at {start:#x}')
        require(len(decoded) == int(row['decoded_bytes']), f'decoded size differs at {start:#x}')
        chain_start = int(row['chain_start'], 16)
        segments = by_chain[chain_start]
        if segments:
            _, previous_end, previous = segments[-1]
            require(len(previous) == CHUNK_SIZE, f'short continuation predecessor at {start:#x}')
            require(start == (previous_end + 15) & ~15, f'unaligned continuation at {start:#x}')
            require(not any(data[previous_end:start]), f'nonzero continuation gap at {start:#x}')
        else:
            require(chain_start == start, f'invalid first stream offset at {start:#x}')
        segments.append((start, stop, decoded))
    require(cursor == end, 'range map ends early')
    return rows, by_chain


def verify_psin(segments):
    require(len(segments) in (1, 2), 'unexpected PSIN stream count')
    data = b''.join(chunk for _, _, chunk in segments)
    cursor = 0
    tags = []
    while cursor < len(data):
        tag, size = struct.unpack_from('>4sI', data, cursor)
        require(8 <= size <= len(data) - cursor, 'invalid PSIN section size')
        tags.append(tag)
        cursor += size
    require(
        tags == [b'PSIN', b'LSCH', b'LENM', b'LSNS', b'LGID', b'LRSC', b'CHKS'],
        'unexpected PSIN sections',
    )
    require(struct.unpack_from('>I', data, cursor - size + 8)[0] == len(data), 'CHKS size differs')


def verify_offset_object(segments):
    lengths = [len(chunk) for _, _, chunk in segments]
    require(len(lengths) >= 2 and all(n == CHUNK_SIZE for n in lengths[:-1]), 'invalid object chunk sizes')
    require(0 < lengths[-1] < CHUNK_SIZE, 'expected a short final chunk')
    data = b''.join(chunk for _, _, chunk in segments)
    count = struct.unpack_from('<I', data, 0x14)[0]
    table_end = 0x28 + count * 8
    require(count > 0 and table_end < len(data), 'invalid internal offset table size')
    offsets = struct.unpack_from(f'<{count}Q', data, 0x28)
    require(offsets[0] == table_end, 'first record does not follow the table')
    require(
        all(a < b for a, b in zip(offsets, offsets[1:])) and
        all(offset % 16 == 0 and offset < len(data) for offset in offsets),
        'internal record offsets are unordered, unaligned, or out of bounds',
    )
    require(offsets[-1] >= len(data) - lengths[-1], 'last record does not reach the final chunk')
    addresses = {offset + 8 for offset in offsets}
    references = [
        (position * 8, address)
        for position, (address, tag) in enumerate(struct.iter_unpack('<II', data))
        if tag == 0x71717171
    ]
    require(references and all(address in addresses for _, address in references), 'invalid tagged reference')
    cross = sum(position // CHUNK_SIZE != address // CHUNK_SIZE for position, address in references)
    require(cross > 0, 'no references link separate decoded chunks')
    roots, leaves = verify_record_forest(data, offsets, references)
    return len(data), count, len(references), cross, roots, leaves


def verify_record_forest(data, offsets, references):
    by_address = {offset + 8: index for index, offset in enumerate(offsets)}
    children = [[] for _ in offsets]
    has_parent = set()
    for position, address in references:
        source = bisect_right(offsets, position) - 1
        target = by_address[address]
        require(0 <= source < target, 'tagged reference does not point forward from a record')
        require(target not in has_parent, 'record has multiple tagged parents')
        children[source].append(target)
        has_parent.add(target)

    sizes = [1] * len(offsets)
    root_ids = set()
    for index in range(len(offsets) - 1, -1, -1):
        end = index + 1
        for child in sorted(children[index]):
            require(child == end, 'record subtree is not contiguous')
            end += sizes[child]
        sizes[index] = end - index
        identifier = struct.unpack_from('<I', data, offsets[index])[0]
        if index in has_parent:
            require(identifier == 0, 'child record has a nonzero first word')
        else:
            require(identifier != 0 and identifier not in root_ids, 'invalid root identifier')
            root_ids.add(identifier)
    return len(root_ids), sum(not references for references in children)


def xml_count(by_chain):
    count = 0
    for segments in by_chain.values():
        try:
            ET.fromstring(b''.join(chunk for _, _, chunk in segments))
        except (ET.ParseError, ValueError, LookupError):
            continue
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive_dir', type=Path, help='directory containing the local samples')
    parser.add_argument('--cli', type=Path, default=Path('target/debug/rage-tools-vi'))
    args = parser.parse_args()

    script = args.archive_dir / 'script.rpf'
    data = script.read_bytes()
    small_rows, small = read_map(args.cli, script, data, (0x1000, 0xc3b90))
    require(set(small) == {0x53000}, 'expected one zlib chain in the small embedded pack')
    opaque = [
        (row['start'], row['end'])
        for row in small_rows
        if row['kind'] == 'unclassified'
    ]
    require(opaque == [('0x2010', '0x52fe0')], 'unexpected opaque span in the small pack')
    chain = small[0x53000]
    decoded, offsets, references, cross, roots, leaves = verify_offset_object(chain)
    print(f'script small pack: {len(chain)} streams, 1 structured object, {decoded:,} decoded bytes')
    print(f'  {offsets:,} offsets, {references:,} resolved tagged references, {cross:,} across chunks')
    print(f'  contiguous record trees: {roots:,} roots, {leaves:,} leaves')
    print('  1 opaque range without a verified entry boundary or codec')

    _, large = read_map(args.cli, script, data, (0xc4000, 0x4282b0))
    for segments in large.values():
        verify_psin(segments)
    continuations = sum(len(segments) - 1 for segments in large.values())
    _, root = read_map(args.cli, script, data)
    physical = sum(map(len, root.values()))
    require(physical == len(chain) + len(large) + continuations, 'script stream counts do not reconcile')
    print(f'script large pack: {len(large):,} PSIN objects with {continuations} continuations')
    print(f'script root: {physical:,} verified streams across both embedded packs')
    front = struct.unpack_from('<I', data, 4)[0]
    trailer = len(data) - struct.unpack_from('<I', data, 12)[0]
    require(
        all(not any(data[start:end]) for start, end in (
            (front, 0x1000), (0xc3b90, 0xc4000), (0x4282b0, trailer),
        )),
        'unexpected bytes between the observed embedded pack envelopes',
    )
    print('  both candidate embedded pack envelopes cover all nonzero payload bytes')

    for name in ('story000_bvh4.rpf', 'common.rpf'):
        path = args.archive_dir / name
        data = path.read_bytes()
        rows, chains = read_map(args.cli, path, data)
        opaque = [row for row in rows if row['kind'] == 'unclassified']
        count = struct.unpack_from('<I', data, 0x24)[0]
        print(
            f'{name}: {sum(map(len, chains.values()))} verified streams, '
            f'{len(chains)} candidate zlib chains, {xml_count(chains)} complete XML documents, '
            f'{len(opaque)} unclassified spans '
            f'({sum(int(row["stored_bytes"]) for row in opaque):,} bytes), header +0x24={count}'
        )


if __name__ == '__main__':
    main()
