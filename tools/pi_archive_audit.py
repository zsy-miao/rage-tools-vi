#!/usr/bin/env python3
"""Archive-only reproduction for the RPF9 payload audit.

Usage: python3 tools/pi_archive_audit.py . [--cli target/debug/rage-tools-vi]
The archive checkout is only read. No executables, keys, decryption, or filename
recovery are used.
"""

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
import zlib

CHUNK = 65536
CLORDER = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]
LENBASE = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43,
           51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258]
LENEXTRA = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3,
            4, 4, 4, 4, 5, 5, 5, 5, 0]
DISTBASE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193,
            257, 385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193,
            12289, 16385, 24577]
DISTEXTRA = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8,
             9, 9, 10, 10, 11, 11, 12, 12, 13, 13]


class Bits:
    def __init__(self, data, pos=0):
        self.data, self.pos = data, pos

    def bit(self):
        p = self.pos
        self.pos += 1
        return (self.data[p >> 3] >> (p & 7)) & 1

    def get(self, n):
        return sum(self.bit() << i for i in range(n))


def huffman(lengths):
    maxbits = max(lengths) if lengths else 0
    counts = [0] * (maxbits + 1)
    for length in lengths:
        if length:
            counts[length] += 1
    code = 0
    nextcode = [0] * (maxbits + 1)
    for bits in range(1, maxbits + 1):
        code = (code + counts[bits - 1]) << 1
        nextcode[bits] = code
    table = {}
    for symbol, length in enumerate(lengths):
        if length:
            c = nextcode[length]
            nextcode[length] += 1
            table[(length, int(f'{c:0{length}b}'[::-1], 2))] = symbol
    return table, maxbits


def huff_symbol(bits, table, maxbits):
    code = 0
    for length in range(1, maxbits + 1):
        code |= bits.bit() << (length - 1)
        if (length, code) in table:
            return table[(length, code)]
    raise ValueError(f'invalid Huffman code at bit {bits.pos}')


def deflate_blocks(data):
    """Return (decoded, [(start_bit, final, type, out_start, out_end, end_bit)], error)."""
    bits, out, blocks = Bits(data), bytearray(), []
    try:
        while True:
            start_bit, out_start = bits.pos, len(out)
            final, btype = bits.bit(), bits.get(2)
            if btype == 0:
                bits.pos = (bits.pos + 7) & ~7
                p = bits.pos >> 3
                length = data[p] | data[p + 1] << 8
                if length ^ (data[p + 2] | data[p + 3] << 8) != 0xffff:
                    raise ValueError('invalid stored block lengths')
                bits.pos = (p + 4) * 8
                out += data[bits.pos >> 3:(bits.pos >> 3) + length]
                bits.pos += length * 8
            else:
                if btype == 1:
                    lit = [8] * 144 + [9] * 112 + [7] * 24 + [8] * 8
                    dist = [5] * 32
                elif btype == 2:
                    hlit, hdist, hclen = bits.get(5) + 257, bits.get(5) + 1, bits.get(4) + 4
                    cl = [0] * 19
                    for i in range(hclen):
                        cl[CLORDER[i]] = bits.get(3)
                    cltable, clmax = huffman(cl)
                    lengths = []
                    while len(lengths) < hlit + hdist:
                        sym = huff_symbol(bits, cltable, clmax)
                        if sym < 16:
                            lengths.append(sym)
                        elif sym == 16:
                            lengths += [lengths[-1]] * (bits.get(2) + 3)
                        elif sym == 17:
                            lengths += [0] * (bits.get(3) + 3)
                        else:
                            lengths += [0] * (bits.get(7) + 11)
                        if len(lengths) > hlit + hdist:
                            raise ValueError(
                                f'invalid bit-length repeat: {len(lengths)} > {hlit+hdist}')
                    lit, dist = lengths[:hlit], lengths[hlit:]
                else:
                    raise ValueError(f'invalid block type {btype}')
                ltable, lmax = huffman(lit)
                dtable, dmax = huffman(dist)
                while True:
                    sym = huff_symbol(bits, ltable, lmax)
                    if sym < 256:
                        out.append(sym)
                    elif sym == 256:
                        break
                    else:
                        i = sym - 257
                        length = LENBASE[i] + bits.get(LENEXTRA[i])
                        ds = huff_symbol(bits, dtable, dmax)
                        distance = DISTBASE[ds] + bits.get(DISTEXTRA[ds])
                        if distance > len(out):
                            raise ValueError(f'invalid distance {distance} > {len(out)}')
                        for _ in range(length):
                            out.append(out[-distance])
            blocks.append((start_bit, final, btype, out_start, len(out), bits.pos))
            if final:
                break
        return bytes(out), blocks, None
    except Exception as error:
        return bytes(out), blocks, (str(error), bits.pos)


def map_rows(cli, archive, bounds=None):
    args = [str(cli), 'map', str(archive)] + ([f'{x:x}' for x in bounds] if bounds else [])
    text = subprocess.check_output(args, text=True)
    return list(csv.DictReader(text.splitlines(), delimiter='\t'))


def decode_chains(data, rows):
    chains = defaultdict(list)
    for row in rows:
        if row['kind'] == 'zlib':
            chains[int(row['chain_start'], 16)].append(
                (int(row['start'], 16), int(row['end'], 16)))
    return {start: b''.join(zlib.decompressobj().decompress(data[a:b]) for a, b in streams)
            for start, streams in chains.items()}


def task1(archive_dir):
    print('\n[1] common.rpf partial streams')
    data = (archive_dir / 'common.rpf').read_bytes()
    rows = map_rows(CLI, archive_dir / 'common.rpf')
    chains = decode_chains(data, rows)
    for start, end in ((0x212190, 0x212f20), (0x21ba50, 0x21d0dd)):
        span = data[start:end]
        inflater, decoded, fail, eof = zlib.decompressobj(-15), b'', None, None
        for i in range(2, len(span)):
            try:
                decoded += inflater.decompress(span[i:i + 1])
            except Exception as error:
                fail = (start + i, str(error))
                break
            if inflater.eof:
                eof = start + i + 1
                break
        print(f'range {start:#x}..{end:#x}, wrapper {span[:2].hex()}, raw starts {start+2:#x}')
        if fail:
            print(f'  failure {fail[0]:#x} after {len(decoded):,} decoded bytes: {fail[1]}')
            preceding = chains.get(0x210a70, b'')
            print(f'  predecessor chain 0x210a70 decodes {len(preceding):,} bytes; '
                  f'last bytes {preceding[-40:]!r}; decoded prefix {decoded[:40]!r}')
            parsed, blocks, error = deflate_blocks(span[2:])
            print(f'  parsed blocks: {[(b[0], b[1], b[2], b[3], b[4], b[5]) for b in blocks]}; error={error}')
        if eof:
            stored = struct.unpack('>I', span[eof - start:eof - start + 4])[0]
            calculated = zlib.adler32(decoded) & 0xffffffff
            print(f'  raw end {eof:#x}, {len(decoded):,} decoded bytes, stored Adler {stored:08x}, '
                  f'calculated {calculated:08x}, bytes after end {len(span)-(eof-start)}, after 4-byte trailer {len(span)-(eof-start)-4}')
            parsed, blocks, error = deflate_blocks(span[2:eof - start])
            print(f'  parsed blocks: {[(b[0], b[1], b[2], b[3], b[4], b[5]) for b in blocks]}; error={error}')
            preceding = chains.get(0x21ad30, b'')
            print(f'  predecessor chain 0x21ad30 decodes {len(preceding):,} bytes; '
                  f'last bytes {preceding[-40:]!r}; decoded prefix {decoded[:40]!r}')
            print(f'  first malformed tag in this stream at decoded offset {first_malformed(decoded):#x}')


def first_malformed(data):
    import re
    pattern = re.compile(rb'</?[A-Za-z_][A-Za-z0-9_.:-]*( [^>]*)?/?>')
    for match in re.finditer(rb'<[^>]*>', data):
        if not pattern.fullmatch(match.group()):
            return match.start()
    return -1


def task2(archive_dir):
    print('\n[2] root IDs versus PSIN records')
    script = (archive_dir / 'script.rpf').read_bytes()
    obj_path = Path('/tmp/pi-script-small.bin')
    if obj_path.exists():
        obj_path.unlink()
    subprocess.check_call([str(CLI), 'extract-zlib', str(archive_dir / 'script.rpf'),
                           '53000', 'c3b45', str(obj_path)], stdout=subprocess.DEVNULL)
    obj = obj_path.read_bytes()
    count = struct.unpack_from('<I', obj, 0x14)[0]
    offsets = list(struct.unpack_from(f'<{count}Q', obj, 0x28))
    sizes = [(offsets[i + 1] if i + 1 < len(offsets) else len(obj)) - offsets[i]
             for i in range(count)]
    by_address = {offset + 8: i for i, offset in enumerate(offsets)}
    parents, refs = set(), []
    for position, (address, tag) in enumerate(struct.iter_unpack('<II', obj)):
        if tag == 0x71717171:
            refs.append(position * 8)
            parents.add(by_address[address])
    roots = [i for i in range(count) if i not in parents]
    root_ids = [struct.unpack_from('<I', obj, offsets[i])[0] for i in roots]
    print(f'42-stream object: {len(obj):,} bytes, {count:,} records, {len(roots)} roots, '
          f'{len(refs):,} tagged references; root sizes {Counter(sizes[i] for i in roots)}')
    relative = Counter()
    import bisect
    for position in refs:
        source = bisect.bisect_right(offsets, position) - 1
        relative[position - offsets[source]] += 1
    print(f'  tagged-reference record-relative positions: {relative.most_common(6)}')
    print(f'  relative positions mod 16: {Counter(k % 16 for k in relative)}')

    rows = map_rows(CLI, archive_dir / 'script.rpf', (0xc4000, 0x4282b0))
    chains = decode_chains(script, rows)
    records, total_windows = [], 0
    for chain, record in sorted(chains.items()):
        pos, sections = 0, []
        while pos < len(record):
            tag, size = struct.unpack_from('>4sI', record, pos)
            sections.append((tag.decode(), pos, size))
            pos += size
        records.append((chain, record, sections))
        total_windows += max(0, len(record) - 3)
    lgid = [section[2] for _, _, sections in records for section in sections if section[0] == 'LGID']
    print(f'PSIN records: {len(records)}, LGID section sizes {Counter(lgid)}, '
          f'total 32-bit windows {total_windows:,}')
    idset = {value: index for index, value in enumerate(root_ids)}
    matches = []
    for ri, (chain, record, sections) in enumerate(records):
        for offset in range(len(record) - 3):
            little = struct.unpack_from('<I', record, offset)[0]
            big = struct.unpack_from('>I', record, offset)[0]
            if little in idset:
                matches.append((idset[little], ri, chain, offset, 'little', little, sections))
            if big in idset and big != little:
                matches.append((idset[big], ri, chain, offset, 'big', big, sections))
    expected = 2 * len(idset) * total_windows / 2**32
    print(f'  direct coincidences: {len(matches)}; random expectation {expected:.2f}')
    for idx, ri, chain, offset, order, value, sections in matches:
        section = next(s for s in sections if s[1] <= offset < s[1] + s[2])
        print(f'  root[{idx}]={value:#010x} record {ri} chain {chain:#x} length {len(records[ri][1]):,} '
              f'offset {offset:#x} {order} section {section[0]}+{offset-section[1]:#x}')


def task3(archive_dir):
    print('\n[3] script.rpf opaque-span motif')
    script = (archive_dir / 'script.rpf').read_bytes()
    span_start, span_end = 0x2010, 0x52fe0
    raw = script[span_start:span_end]
    off = 0x14470
    period = raw[off:off + 7]
    run = 0
    while raw[off + run:off + run + 7] == period:
        run += 7
    print(f'period {period.hex()} repeats {run // 7} times from raw {off:#x} to {off+run:#x} '
          f'(archive {span_start+off:#x}..{span_start+off+run:#x}), length {run}')
    block112 = raw[off:off + 112]
    print(f'112-byte snapshot = 16 periods; sha256 {__import__("hashlib").sha256(block112).hexdigest()}')
    blocks = [block112[i:i + 16] for i in range(0, 112, 16)]
    spans = {}
    for name in ('common.rpf', 'script.rpf', 'core_licenses_data.rpf', 'appdata0.rpf'):
        rows = map_rows(CLI, archive_dir / name)
        spans[name] = [(int(r['start'], 16), int(r['end'], 16))
                       for r in rows if r['kind'] == 'unclassified']
    print(f'searched opaque spans: {sum(len(v) for v in spans.values())} spans '
          f'{ {k: len(v) for k, v in spans.items()} }')
    for index, block in enumerate(blocks):
        hits = []
        for name, ranges in spans.items():
            data = (archive_dir / name).read_bytes()
            for start, end in ranges:
                for pos in range((start + 15) // 16 * 16, end - 15, 16):
                    if data[pos:pos + 16] == block:
                        hits.append((name, pos))
        outside = [(n, p) for n, p in hits
                   if not (n == 'script.rpf' and span_start + off <= p < span_start + off + run)]
        print(f'  16-byte block {index}: {len(hits)} hits, {len(outside)} outside motif run; '
              f'{[hex(p) for _, p in hits]}')


def task4(archive_dir):
    print('\n[4] common.rpf metadata/count evidence')
    common = (archive_dir / 'common.rpf').read_bytes()
    rows = map_rows(CLI, archive_dir / 'common.rpf')
    chains = decode_chains(common, rows)
    opaque = [r for r in rows if r['kind'] == 'unclassified']
    xml = 0
    for record in chains.values():
        try:
            ET.fromstring(record)
            xml += 1
        except Exception:
            pass
    print(f'header +0x24={struct.unpack_from("<I", common, 0x24)[0]}, '
          f'checksum-valid streams={sum(1 for r in rows if r["kind"] == "zlib")}, '
          f'candidate zlib chains={len(chains)}, complete XML={xml}, '
          f'opaque spans={len(opaque)}, candidate groups={len(chains)+len(opaque)}, '
          f'confirmed archive entries=0')
    out = archive_dir / 'output' / 'common.rpf'
    docs = {p.name: p.read_text(errors='ignore') for p in out.glob('*.xml')}
    ids = {}
    for name, text in docs.items():
        try:
            elem = ET.fromstring(text).find('id')
        except Exception:
            continue
        if elem is not None and elem.text:
            ids[name] = elem.text
    paths = []
    for doc, value in sorted(ids.items()):
        suffix = 'ccs_' + value + '.meta'
        hit = next((line.strip() for text in docs.values() for line in text.splitlines()
                    if suffix in line and 'loadPath' in line), None)
        if hit:
            paths.append('$(root)/changesets/' + suffix)
            print(f'  XML association {doc}: id={value} -> {hit}')
    hmap = next((line.strip() for text in docs.values() for line in text.splitlines()
                 if 'heightmap.dat' in line), None)
    if hmap:
        paths.append('common:/data/levels/americas/heightmap.dat')
        print(f'  HMAP path association: {hmap}')
    trie = set()
    for path in paths:
        parts = path.split('/')
        for i in range(1, len(parts) + 1):
            trie.add('/'.join(parts[:i]))
    print(f'  same-archive candidate paths={len(paths)}, trie nodes={len(trie)} '
          f'(leaves {len(paths)}, directory/prefix nodes {len(trie)-len(paths)})')
    print('  no decoded index record; a trie over eight paths cannot decide whether +0x24 counts files, directories, or both')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive_dir', type=Path)
    parser.add_argument('--cli', type=Path,
                        default=Path('target/debug/rage-tools-vi'))
    args = parser.parse_args()
    CLI = args.cli
    task1(args.archive_dir)
    task2(args.archive_dir)
    task3(args.archive_dir)
    task4(args.archive_dir)
