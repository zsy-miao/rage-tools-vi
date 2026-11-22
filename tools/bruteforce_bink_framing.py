#!/usr/bin/env python3
"""Parallel framing sweep for AWC payload -> Bink Audio decoder."""
import csv
import math
import mmap
import os
import struct
import subprocess
import tempfile
import wave
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np

DEC = Path('/tmp/rawdecode2')
OUT = Path('output/audio-tests/bruteforce')
_CHUNK = b''
_OUT = OUT


def chunks_from_awc(path, cap=512 * 1024):
    with path.open('rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        dataoff = struct.unpack_from('<I', mm, 12)[0]
        known = {0x55, 0x36, 0x76, 0xA3, 0xFA, 0x48, 0x5C, 0x68, 0x2B, 0x5A, 0xD9, 0xBD}
        for n in range(1, min(40000, dataoff // 8) + 1):
            start = dataoff - 8 * n
            cs = []
            ok = True
            for pos in range(start, dataoff, 8):
                raw = struct.unpack_from('<Q', mm, pos)[0]
                typ, size, off = raw >> 56, (raw >> 28) & 0x0FFFFFFF, raw & 0x0FFFFFFF
                if typ not in known or not size or off + size > len(mm):
                    ok = False
                    break
                if typ == 0x55:
                    cs.append(mm[off:off + size])
            if ok and cs:
                mm.close()
                return [c[:cap] for c in cs]
        mm.close()
        return []


def shift(data, bits):
    if bits == 0:
        return data
    out = bytearray(len(data) - 1)
    for i in range(len(out)):
        out[i] = ((data[i] << bits) | (data[i + 1] >> (8 - bits))) & 0xFF
    return bytes(out)


def score(path):
    if not path.is_file() or path.stat().st_size <= 44:
        return None
    with wave.open(str(path), 'rb') as w:
        rate = w.getframerate()
        raw = w.readframes(min(w.getnframes(), rate * 2))
    x = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768
    if len(x) < 1024:
        return None
    p = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2 + 1e-20
    f = np.fft.rfftfreq(len(x), 1 / rate)
    p = p[(f >= 20) & (f <= 20000)]
    flat = float(np.exp(np.mean(np.log(p))) / np.mean(p))
    share = float(np.max(p) / np.sum(p))
    ac = np.correlate(x, x, 'full')[len(x)-1:]
    ac /= (ac[0] + 1e-20)
    harmonic = float(np.max(ac[rate // 2000: rate // 50])) if len(ac) > rate // 50 else 0.0
    return flat, share, harmonic, len(x)


def init_worker(chunk, outdir):
    global _CHUNK, _OUT
    _CHUNK = chunk
    _OUT = Path(outdir)
    (_OUT / 'hits').mkdir(parents=True, exist_ok=True)


def try_candidate(candidate):
    bits, off, codec, ch = candidate
    data = shift(_CHUNK, bits)
    payload = data[off:]
    if len(payload) < 2048:
        return None
    tag = f'{os.getpid()}-{bits}-{off}-{codec}-{ch}'
    pkt = _OUT / f'p-{tag}.bin'
    wav = _OUT / f'p-{tag}.wav'
    with pkt.open('wb') as f:
        f.write(struct.pack('<I', len(payload)))
        f.write(payload)
    r = subprocess.run([str(DEC), codec, str(ch), str(pkt), str(wav), '2'], capture_output=True, text=True)
    s = score(wav)
    if s is None:
        pkt.unlink(missing_ok=True); wav.unlink(missing_ok=True)
        return None
    flat, share, harm, n = s
    keep = flat < 0.2 or harm > 0.2
    if keep:
        hit = _OUT / 'hits' / f'{tag}.wav'
        wav.replace(hit)
    else:
        wav.unlink(missing_ok=True)
    pkt.unlink(missing_ok=True)
    return (flat, -harm, share, codec, ch, bits, off, n, str(hit) if keep else '', (r.stderr or '').strip().splitlines()[-1] if (r.stderr or '').strip() else '')


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=min(32, os.cpu_count() or 4))
    parser.add_argument('--max-bits', type=int, default=8)
    parser.add_argument('--max-offset', type=int, default=64)
    args = parser.parse_args()
    if not DEC.is_file():
        raise SystemExit(f'decoder missing: {DEC}')
    manifest = list(csv.DictReader(Path('output/extracted/audio-awc/manifest.tsv').open(), delimiter='\t'))
    row = max(manifest, key=lambda r: int(r['bytes']))
    chunks = chunks_from_awc(Path(row['path']))
    if not chunks:
        raise SystemExit('no data chunks')
    chunk = chunks[0]
    OUT.mkdir(parents=True, exist_ok=True)
    candidates = [(bits, off, codec, ch)
                  for bits in range(args.max_bits)
                  for off in range(args.max_offset + 1)
                  for codec in ('binkaudio_dct', 'binkaudio_rdft')
                  for ch in (1, 2)]
    print('source', row['path'], 'chunk', len(chunk), 'candidates', len(candidates), 'workers', args.workers)
    results = []
    with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker, initargs=(chunk, str(OUT))) as pool:
        futures = [pool.submit(try_candidate, c) for c in candidates]
        for i, fut in enumerate(as_completed(futures), 1):
            r = fut.result()
            if r:
                results.append(r)
                if r[8]:
                    print('HIT', r)
            if i % 200 == 0:
                print('done', i, 'results', len(results))
    results.sort()
    with (OUT / 'results.tsv').open('w', newline='') as f:
        w = csv.writer(f, delimiter='\t', lineterminator='\n')
        w.writerow(['flatness', 'neg_harmonic', 'max_bin_share', 'codec', 'channels', 'bit_offset', 'byte_offset', 'samples', 'hit', 'decoder'])
        w.writerows(results[:500])
    print('top')
    for r in results[:20]:
        print(r)


if __name__ == '__main__':
    main()
