#!/usr/bin/env python3
"""Sweep AWC data payload offsets through a synthetic UEBA/Bink Audio wrapper."""
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

VGM = Path('/tmp/vgmstream/build/cli/vgmstream-cli')
OUT = Path('output/audio-tests/ueba-sweep')
_CHUNKS = []
_META = []


def parse_source():
    manifest = list(csv.DictReader(Path('output/extracted/audio-awc/manifest.tsv').open(), delimiter='\t'))
    # use first few AWC files with multiple streams
    chunks = []
    meta = []
    for row in manifest[:20]:
        with open(row['path'], 'rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            dataoff = struct.unpack_from('<I', mm, 12)[0]
            known = {0x55, 0x36, 0x76, 0xA3, 0xFA, 0x48, 0x5C, 0x68, 0x2B, 0x5A, 0xD9, 0xBD}
            table = None
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
                    cs.append((typ, size, off))
                if ok and any(t == 0x55 for t, _, _ in cs):
                    table = cs
                    break
            if table:
                data = [mm[o:o+s] for t, s, o in table if t == 0x55]
                fmt = next((mm[o:o+s] for t, s, o in table if t == 0x76), None)
                if data and fmt:
                    num = struct.unpack_from('<I', fmt, 0)[0]
                    rate = struct.unpack_from('<H', fmt, 8)[0]
                    chunks.append(data[0][:256 * 1024])
                    meta.append((num, rate))
            mm.close()
    return chunks, meta


def metrics(path):
    if not path.is_file() or path.stat().st_size <= 44:
        return None
    with wave.open(str(path), 'rb') as w:
        rate = w.getframerate()
        raw = w.readframes(min(w.getnframes(), rate * 2))
    x = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768
    if len(x) < 1024:
        return None
    rms = float(np.sqrt(np.mean(x * x)))
    if rms < 1e-5:
        return None
    p = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2 + 1e-20
    f = np.fft.rfftfreq(len(x), 1 / rate)
    p = p[(f >= 20) & (f <= 20000)]
    flat = float(np.exp(np.mean(np.log(p))) / np.mean(p))
    ac = np.correlate(x, x, 'full')[len(x)-1:]
    ac /= ac[0] + 1e-20
    harm = float(np.max(ac[rate // 2000: rate // 50])) if len(ac) > rate // 50 else 0.0
    return rms, flat, harm, len(x)


def init_worker(chunks, meta):
    global _CHUNKS, _META
    _CHUNKS = chunks
    _META = meta


def try_one(task):
    idx, off = task
    data = _CHUNKS[idx]
    num, rate = _META[idx]
    if off >= len(data) - 1024:
        return None
    payload = data[off:]
    header = struct.pack('<4sBBHIIHHIHH', b'ABEU', 1, 1, 0, rate, num, min(len(payload), 0xffff), 1, 0x1c + 4 + len(payload), 0, 1)
    packet = struct.pack('<HH', 0x9999, len(payload)) + payload
    tag = f'{os.getpid()}-{idx}-{off}'
    src = OUT / f'{tag}.ueba'
    wav = OUT / f'{tag}.wav'
    src.write_bytes(header + packet)
    r = subprocess.run([str(VGM), '-o', str(wav), str(src)], capture_output=True, text=True)
    m = metrics(wav)
    if m:
        rms, flat, harm, n = m
        keep = rms > 0.001 and (flat < 0.35 or harm > 0.15)
        if keep:
            dst = OUT / 'hits' / f'{tag}.wav'
            wav.replace(dst)
        else:
            wav.unlink(missing_ok=True)
        src.unlink(missing_ok=True)
        return (flat, -harm, rms, idx, off, n, str(dst) if keep else '', (r.stdout or r.stderr or '').strip().splitlines()[:2])
    src.unlink(missing_ok=True); wav.unlink(missing_ok=True)
    return None


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=min(32, os.cpu_count() or 4))
    parser.add_argument('--max-offset', type=int, default=256)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'hits').mkdir(exist_ok=True)
    chunks, meta = parse_source()
    print('chunks', len(chunks), 'offsets', args.max_offset)
    tasks = [(i, off) for i in range(len(chunks)) for off in range(args.max_offset + 1)]
    results = []
    with ProcessPoolExecutor(max_workers=args.workers, initializer=init_worker, initargs=(chunks, meta)) as pool:
        futures = [pool.submit(try_one, t) for t in tasks]
        for i, fut in enumerate(as_completed(futures), 1):
            r = fut.result()
            if r:
                results.append(r)
                if r[6]: print('HIT', r)
            if i % 500 == 0: print('done', i, 'results', len(results))
    results.sort()
    with (OUT / 'results.tsv').open('w', newline='') as f:
        w = csv.writer(f, delimiter='\t', lineterminator='\n')
        w.writerow(['flatness', 'neg_harmonic', 'rms', 'chunk', 'offset', 'samples', 'hit', 'decoder'])
        w.writerows(results[:500])
    print('top')
    for r in results[:20]: print(r)


if __name__ == '__main__':
    main()
