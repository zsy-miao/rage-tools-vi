#!/usr/bin/env python3
"""Test an inverse real FFT on a bounded set of codec 0x02 controls."""

import argparse
import ctypes
from ctypes.util import find_library
import math
from pathlib import Path
import struct

from data_awc_opus_probe import stream_chunks
from data_awc_trim_controls import FOOTER_SIZE, parse_ace1


FFT_SIZE = FOOTER_SIZE // 4
HOP = FFT_SIZE // 2
FFTW_ESTIMATE = 64
MAX_RELATIVE_ERROR = 0.005


class InverseFFT:
    def __init__(self):
        library = find_library("fftw3")
        if not library:
            raise RuntimeError("libfftw3 is required")
        self.lib = ctypes.CDLL(library)
        pointer = ctypes.POINTER(ctypes.c_double)
        self.lib.fftw_plan_dft_c2r_1d.argtypes = [ctypes.c_int, pointer, pointer, ctypes.c_uint]
        self.lib.fftw_plan_dft_c2r_1d.restype = ctypes.c_void_p
        self.lib.fftw_execute.argtypes = [ctypes.c_void_p]
        self.lib.fftw_execute.restype = None
        self.lib.fftw_destroy_plan.argtypes = [ctypes.c_void_p]
        self.lib.fftw_destroy_plan.restype = None
        self.input = (ctypes.c_double * (FFT_SIZE + 2))()
        self.output = (ctypes.c_double * FFT_SIZE)()
        self.plan = self.lib.fftw_plan_dft_c2r_1d(FFT_SIZE, self.input, self.output, FFTW_ESTIMATE)
        if not self.plan:
            raise RuntimeError("FFTW could not create its inverse plan")

    def inverse(self, words):
        self.input[:FFT_SIZE] = words
        self.input[FFT_SIZE] = 0
        self.input[FFT_SIZE + 1] = 0
        self.lib.fftw_execute(self.plan)
        return [value / FFT_SIZE for value in self.output]

    def close(self):
        self.lib.fftw_destroy_plan(self.plan)


def rms(values):
    return math.sqrt(sum(value * value for value in values) / len(values))


def alternating_mean(values):
    return sum(value if index % 2 == 0 else -value for index, value in enumerate(values)) / len(values)


def restore_nyquist(windows):
    """Recover the missing alternating component using the zero prefix and overlaps."""
    correction = -alternating_mean(windows[0][:HOP])
    corrections = [correction]
    for left, right in zip(windows, windows[1:]):
        difference = [a - b for a, b in zip(left[HOP:], right[:HOP])]
        correction += alternating_mean(difference)
        corrections.append(correction)
    return [
        [value + (delta if index % 2 == 0 else -delta) for index, value in enumerate(window)]
        for window, delta in zip(windows, corrections)
    ]


def reconstruct(floats, ir_length, transform):
    tiles = [
        struct.unpack_from(f"<{FFT_SIZE}f", floats, offset)
        for offset in range(0, len(floats), FOOTER_SIZE)
    ]
    nonzero_indexes = [index for index, tile in enumerate(tiles) if any(tile)]
    needed = math.ceil(ir_length / HOP)
    if ir_length <= 0 or nonzero_indexes != list(range(needed + 1)):
        raise ValueError("nonzero transform extent disagrees with declared impulse length")
    windows = restore_nyquist([transform.inverse(tile) for tile in tiles[:needed + 1]])
    reconstructed = [value for window in windows[:-1] for value in window[HOP:]]
    differences = [
        a - b
        for left, right in zip(windows, windows[1:])
        for a, b in zip(left[HOP:], right[:HOP])
    ]
    impulse = reconstructed[:ir_length]
    tail = rms(reconstructed[ir_length:] + windows[-1][HOP:])
    levels = (rms(impulse), tail, rms(differences), rms(windows[0][:HOP]))
    if max(levels[1:]) > levels[0] * MAX_RELATIVE_ERROR:
        raise ValueError(f"overlap or zero padding disagrees with inverse FFT: {levels}")
    return impulse, len(nonzero_indexes), levels


def write_float_wav(path, rate, impulse):
    fmt = struct.pack("<HHIIHH", 3, 1, rate, rate * 4, 4, 32)
    chunks = [
        (b"fmt ", fmt),
        (b"fact", struct.pack("<I", len(impulse))),
        (b"data", struct.pack(f"<{len(impulse)}f", *impulse)),
    ]
    body = b"WAVE" + b"".join(tag + struct.pack("<I", len(data)) + data for tag, data in chunks)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("awc", type=Path)
    parser.add_argument("--output", type=Path, help="write reconstructed float WAV impulse responses")
    args = parser.parse_args()
    transform = InverseFFT()
    print("stream\tbody_offset\tdeclared_taps\tnonzero_blocks"
          "\tinside_rms\tafter_rms\toverlap_error_rms\tleading_rms\tfile")
    try:
        for index, chunks in stream_chunks(args.awc):
            if not all(key in chunks for key in (0x55, 0x76)):
                continue
            _, fmt = chunks[0x76]
            if fmt[0x1C] != 0x02:
                continue
            offset, payload = chunks[0x55]
            allocated = struct.unpack_from("<I", fmt)[0]
            rate = struct.unpack_from("<H", fmt, 8)[0]
            ir_length = struct.unpack_from("<I", fmt, 0x0C)[0]
            floats, _, _ = parse_ace1(payload, allocated)
            impulse, blocks, levels = reconstruct(floats, ir_length, transform)
            path = ""
            if args.output:
                args.output.mkdir(parents=True, exist_ok=True)
                path = args.output / f"stream-{index:02d}.wav"
                write_float_wav(path, rate, impulse)
            print(index, hex(offset), ir_length, blocks, *(f"{level:.7g}" for level in levels), path, sep="\t")
    finally:
        transform.close()


if __name__ == "__main__":
    main()
