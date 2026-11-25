#!/usr/bin/env python3
"""Re-test only the failed rows of the existing AWC Opus manifest."""

import argparse
from collections import Counter
import csv
from fractions import Fraction
from pathlib import Path
import struct
import subprocess
import wave

from data_awc_opus_probe import BLOCK_BYTES, RATE, decode_packets, load_opus, split_block, streams


def seek_scale(counts, last, expected, rate, channels):
    if not expected:
        return "missing"
    if len(counts) != len(expected):
        return "count_mismatch"
    for scale in dict.fromkeys((Fraction(1), Fraction(channels), Fraction(rate, RATE), Fraction(rate * channels, RATE))):
        if [count * scale for count in (*counts[:-1], last)] == expected:
            return str(scale)
    return "offset_mismatch"


def investigate(lib, path, target, directory, resample):
    for stream, codec, sub_id, rate, declared, offset, payload, seek in streams(path):
        if stream != target:
            continue
        if codec != 0x0B:
            raise ValueError(f"unexpected codec {codec:#x}")
        pcm, channels, counts, packets, last, first = decode_packets(lib, payload)
        size = len(seek) & ~3
        expected = list(struct.unpack(f"<{size // 4}I", seek[:size]))
        scale = seek_scale(counts, last, expected, rate, channels)
        if not any(pcm) and scale in {"missing", "count_mismatch", "offset_mismatch"}:
            raise ValueError("silence with an unvalidated seek table")
        if directory:
            directory.mkdir(parents=True, exist_ok=True)
            name = f"{path.stem}-s{stream:02d}"
            target_wav = directory / f"{name}.wav"
            with wave.open(str(target_wav), "wb") as wav:
                wav.setnchannels(channels)
                wav.setsampwidth(2)
                wav.setframerate(RATE)
                wav.writeframes(pcm)
            if resample and RATE != rate:
                resampled = directory / f"{name}-{rate}hz.wav"
                subprocess.run([
                    "ffmpeg", "-v", "error", "-y", "-i", str(target_wav),
                    "-ar", str(rate), str(resampled),
                ], check=True)
        payload_packets = [
            packet
            for start in range(0, len(payload), BLOCK_BYTES)
            for _, packet in split_block(payload[start:start + BLOCK_BYTES])
        ]
        sizes = Counter(map(len, payload_packets))
        size_counts = ",".join(f"{size}:{count}" for size, count in sorted(sizes.items()))
        silent_packets = ",".join(sorted({packet.hex() for packet in payload_packets})) if not any(pcm) else ""
        print(path.name, stream, hex(sub_id), rate, channels, declared, hex(offset), len(payload),
              packets, hex(first[0]), ",".join(map(str, counts)), last, len(seek),
              ",".join(map(str, expected)), seek[size:].hex(), scale, not any(pcm), size_counts,
              silent_packets, sep="\t")
        return
    raise ValueError(f"missing stream {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("handoff/audio-opus-decode.tsv"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resample", action="store_true", help="also write rate-converted copies")
    args = parser.parse_args()
    lib = load_opus()
    print("awc\tstream\tsub_id\trate\tchannels\tdeclared\toffset\tpayload_bytes\tpacket_count\t"
          "first_toc\tdecoded_boundaries_48k\tlast_packet_start_48k\tseek_bytes\tseek_table\t"
          "seek_tail\tseek_scale_from_48k\tsilent\tpacket_size_histogram\tsilent_packet_hex")
    with args.manifest.open(newline="") as source:
        for row in csv.DictReader(source, delimiter="\t"):
            if row["error"]:
                investigate(lib, Path(row["path"]), int(row["stream"]), args.output, args.resample)


if __name__ == "__main__":
    main()
