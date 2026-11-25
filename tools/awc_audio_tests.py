#!/usr/bin/env python3
"""Render raw AWC payload hypotheses to WAV for listening tests."""
import argparse
import csv
import mmap
import struct
import wave
from pathlib import Path

RATE = 48000


def write_wav(path, data, channels=1, width=2, endian='little', signed=True):
    # data already in target byte layout; WAV writes raw frames
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(RATE)
        w.writeframes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('awc', type=Path)
    parser.add_argument('--out-dir', type=Path, default=Path('output/audio-tests'))
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    with args.awc.open('rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        dataoff = struct.unpack_from('<I', mm, 12)[0]
        data = bytearray()
        # The chunk table is data_offset - 8*N. Find N by validating all entries.
        best = None
        for n in range(1, min(20000, dataoff // 8) + 1):
            start = dataoff - 8 * n
            ok = True
            payload = bytearray()
            for pos in range(start, dataoff, 8):
                raw = struct.unpack_from('<Q', mm, pos)[0]
                typ = raw >> 56
                size = (raw >> 28) & 0x0FFFFFFF
                off = raw & 0x0FFFFFFF
                if typ not in (0x55, 0x36, 0x76, 0xA3, 0xFA, 0x48, 0x5C, 0x68, 0x2B, 0x5A, 0xD9, 0xBD) or not size or not (0 <= off < len(mm)) or off + size > len(mm):
                    ok = False
                    break
                if typ == 0x55:
                    payload += mm[off:off+size]
            if ok and payload:
                best = (n, start, payload)
                break
        if best is None:
            raise SystemExit(f'chunk table not found (data_offset={dataoff:#x})')
        n, start, data = best
        print('chunk table', n, 'entries at', hex(start))
        mm.close()
    print('payload', len(data), 'bytes')
    stem = args.awc.stem
    # 16-bit little/big, mono
    write_wav(args.out_dir / f'{stem}-s16le-mono.wav', bytes(data))
    write_wav(args.out_dir / f'{stem}-s16be-mono.wav', b''.join(data[i:i+2][::-1] for i in range(0, len(data)-1, 2)))
    # stereo: interpret interleaved 16-bit
    stereo = len(data) // 4 * 4
    write_wav(args.out_dir / f'{stem}-s16le-stereo.wav', bytes(data[:stereo]), channels=2)
    # 8-bit unsigned
    write_wav(args.out_dir / f'{stem}-u8-mono.wav', bytes((b for b in data)), width=1)
    # float32 LE
    fdata = bytes(data[i:i+4] for i in range(0, 0))
    write_wav(args.out_dir / f'{stem}-f32le-mono.wav', fdata, width=4)
    print('wrote', args.out_dir)
    for p in sorted(args.out_dir.glob('*.wav')):
        print(p, p.stat().st_size)


if __name__ == '__main__':
    main()
