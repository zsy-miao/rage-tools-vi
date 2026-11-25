#!/usr/bin/env python3
"""Measure trim ambiguity and the 0x02 ACE1 trailer on named controls."""

import argparse
import math
from pathlib import Path
import struct
import wave

from data_awc_opus_probe import streams


FOOTER_SIZE = 0x2000
ACE1 = 0xFFFFACE1


def opus_report(awc, directory):
    print("stream\tchannels\traw_frames\tdeclared_units\ttarget_frames\ttotal_trim_frames\t"
          "leading_exact_zero_frames\ttrailing_exact_zero_frames\tfirst_20ms_peak")
    for index, codec, _, rate, declared, _, _, _ in streams(awc):
        if codec != 0x0B:
            continue
        with wave.open(str(directory / f"stream-{index:02d}.wav"), "rb") as wav:
            channels = wav.getnchannels()
            count = wav.getnframes()
            if wav.getsampwidth() != 2 or wav.getframerate() != rate:
                raise ValueError("unexpected control WAV encoding")
            samples = [sample for (sample,) in struct.iter_unpack("<h", wav.readframes(count))]
        if declared % channels:
            raise ValueError("declared count cannot be a whole number of interleaved frames")
        length = declared // channels
        first = next((index for index, sample in enumerate(samples) if sample), len(samples))
        last = next((index for index, sample in enumerate(reversed(samples)) if sample), len(samples))
        peak = max(map(abs, samples[:rate // 50 * channels]))
        print(index, channels, count, declared, length, count - length,
              first // channels, last // channels, peak, sep="\t")


def parse_ace1(payload, declared):
    if len(payload) != 4 * declared or len(payload) < FOOTER_SIZE:
        raise ValueError("unexpected 0x02 payload extent")
    body_size = len(payload) - FOOTER_SIZE
    body, trailer = payload[:body_size], payload[body_size:]
    magic = struct.unpack_from("<I", trailer)[0]
    if magic != ACE1 or body_size % FOOTER_SIZE:
        raise ValueError("ACE1 trailer is not at the expected boundary")
    pairs = list(struct.iter_unpack("<HH", trailer[4:0x40]))
    blocks = body_size // FOOTER_SIZE
    if (pairs[-1][1] != blocks or
            any(a[1] > b[1] for a, b in zip(pairs, pairs[1:])) or any(trailer[0x40:])):
        raise ValueError("ACE1 final pair or trailer padding differs")
    if not all(math.isfinite(value) for (value,) in struct.iter_unpack("<f", body)):
        raise ValueError("0x02 coefficient region contains a nonfinite word")
    return body, trailer, pairs


def ace1_report(path, destination):
    print("stream\tawc_payload_start\tace1_start\tawc_payload_end\tfloat_words\tblocks"
          "\tnonzero_blocks\tall_complex_blocks_conjugate_symmetric\tpairs\tfile")
    for index, codec, _, _, declared, offset, payload, _ in streams(path):
        if codec != 0x02:
            continue
        body, trailer, pairs = parse_ace1(payload, declared)
        nonzero_blocks = 0
        symmetric = True
        for start in range(0, len(body), FOOTER_SIZE):
            points = [complex(*pair) for pair in struct.iter_unpack("<ff", body[start:start + FOOTER_SIZE])]
            if any(points):
                nonzero_blocks += 1
            symmetric &= (
                points[0].imag == points[len(points) // 2].imag == 0
                and all(points[index] == points[-index].conjugate() for index in range(1, len(points) // 2))
            )
        file = ""
        if destination:
            destination.mkdir(parents=True, exist_ok=True)
            file = f"stream-{index:02d}"
            (destination / f"{file}.f32le").write_bytes(body)
            (destination / f"{file}.ace1").write_bytes(trailer)
        print(index, hex(offset), hex(offset + len(body)), hex(offset + len(payload)),
              len(body) // 4, len(body) // FOOTER_SIZE, nonzero_blocks, symmetric,
              ",".join(f"{tag}:{count}" for tag, count in pairs), file, sep="\t")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("awc", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--opus-wavs", type=Path)
    mode.add_argument("--ace1", action="store_true")
    parser.add_argument("--output", type=Path, help="optionally split ACE1 controls into native regions")
    args = parser.parse_args()
    if args.opus_wavs:
        opus_report(args.awc, args.opus_wavs)
    else:
        ace1_report(args.awc, args.output)


if __name__ == "__main__":
    main()
