#!/usr/bin/env python3
"""Scan AWC data chunks for tonal energy in the human 20 Hz-20 kHz band."""
import argparse
import csv
import math
import mmap
import struct
from pathlib import Path

import numpy as np

KNOWN = {0x55, 0x36, 0x76, 0xA3, 0xFA, 0x48, 0x5C, 0x68, 0x2B, 0x5A, 0xD9, 0xBD}
RATES = (48000, 44100, 32000, 24000, 16000)


def data_chunks(mm):
    dataoff = struct.unpack_from('<I', mm, 12)[0]
    for n in range(1, min(40000, dataoff // 8) + 1):
        start = dataoff - 8 * n
        chunks = []
        ok = True
        for pos in range(start, dataoff, 8):
            raw = struct.unpack_from('<Q', mm, pos)[0]
            typ = raw >> 56
            size = (raw >> 28) & 0x0FFFFFFF
            off = raw & 0x0FFFFFFF
            if typ not in KNOWN or not size or off + size > len(mm):
                ok = False
                break
            if typ == 0x55:
                chunks.append(mm[off:off+size])
        if ok and chunks:
            return chunks
    return []


def score(samples, rate):
    if len(samples) < 1024:
        return None
    samples = samples[: min(len(samples), rate * 2)]
    window = np.hanning(len(samples))
    power = np.abs(np.fft.rfft(samples * window)) ** 2 + 1e-20
    freqs = np.fft.rfftfreq(len(samples), 1 / rate)
    band = (freqs >= 20) & (freqs <= 20000)
    p = power[band]
    if len(p) < 16:
        return None
    flatness = float(np.exp(np.mean(np.log(p))) / np.mean(p))
    peak = float(np.max(p) / (np.median(p) + 1e-20))
    total = float(np.sum(p))
    top = float(np.max(p)) / total if total else 0.0
    return flatness, peak, top


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('output/extracted/audio-awc/manifest.tsv'))
    parser.add_argument('--limit', type=int, default=200)
    parser.add_argument('--out', type=Path, default=Path('output/audio-tests/human-range-scan.tsv'))
    args = parser.parse_args()
    rows = list(csv.DictReader(args.manifest.open(), delimiter='\t'))[: args.limit]
    results = []
    for row in rows:
        path = Path(row['path'])
        with path.open('rb') as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            chunks = data_chunks(mm)
            for ci, chunk in enumerate(chunks[:2]):
                for off in (0, 4, 8):
                    raw = chunk[off:]
                    for rate in RATES:
                        for channels, width in ((1, 2), (2, 2), (1, 1)):
                            usable = len(raw) // (channels * width) * channels * width
                            if usable < 2048:
                                continue
                            if width == 1:
                                arr = np.frombuffer(raw[:usable], dtype=np.uint8).astype(np.float32) - 128
                            else:
                                arr = np.frombuffer(raw[:usable], dtype='<i2').astype(np.float32)
                            if channels == 2:
                                arr = arr.reshape(-1, 2).mean(axis=1)
                            sc = score(arr / 32768.0 if width == 2 else arr, rate)
                            if sc:
                                results.append((sc[0], sc[1], sc[2], row['path'], ci, off, rate, channels, width, len(raw)))
            mm.close()
    results.sort(key=lambda r: (r[0], -r[1]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('w', newline='') as f:
        w = csv.writer(f, delimiter='\t', lineterminator='\n')
        w.writerow(['flatness', 'peak_over_median', 'max_bin_share', 'awc', 'chunk', 'offset', 'rate', 'channels', 'width', 'bytes'])
        for r in results[:500]:
            w.writerow([f'{r[0]:.6g}', f'{r[1]:.6g}', f'{r[2]:.6g}', *r[3:]])
    print('candidates', len(results), 'top:')
    for r in results[:15]:
        print(f'flat={r[0]:.5f} peak/med={r[1]:.2f} share={r[2]:.5f} {r[3]} chunk={r[4]} off={r[5]} rate={r[6]} ch={r[7]} w={r[8]}')


if __name__ == '__main__':
    main()
