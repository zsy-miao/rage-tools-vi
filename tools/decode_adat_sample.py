"""Sample streams across containers and measure how many actually decode.

One decoded stream proves the rules; a sample proves the corpus. This walks evenly
spaced containers from the ADAT index, decodes a few streams from each with the same
walker `decode_adat_stream.py` uses, and reports per-variant success, duration and
loudness. Failures are counted with their exception type, so a systematic problem shows
up as a single dominant reason instead of a hash of tracebacks.

    python3 tools/decode_adat_sample.py /src/audio.rpf \\
        --index output/index/audio-adat.tsv --containers 24 --per-container 8
"""

import argparse
import array
import math
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_awc_opus_probe import BLOCK_BYTES, decode_packets, load_opus
from decode_adat_stream import stream_info


def rms(pcm):
    samples = array.array("h")
    samples.frombytes(bytes(pcm))
    if not samples:
        return 0.0
    return math.sqrt(sum(value * value for value in samples) / len(samples))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--index", type=Path, default=Path("output/index/audio-adat.tsv"))
    parser.add_argument("--containers", type=int, default=24)
    parser.add_argument("--per-container", type=int, default=8)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    rows = []
    with args.index.open() as handle:
        import csv
        for row in csv.DictReader(handle, delimiter="\t"):
            rows.append((int(row["start"], 16), int(row["end"], 16)))
    rows.sort()
    if not rows:
        sys.exit("empty index")
    step = max(1, len(rows) // args.containers)
    picked = rows[::step][: args.containers]

    lib = load_opus()
    total = Counter()
    by_flags = defaultdict(Counter)
    durations = []
    loudness = []
    silence = 0
    failures = Counter()
    records = []

    with args.archive.open("rb") as source:
        for start, end in picked:
            source.seek(start)
            blob = source.read(end - start)
            if blob[:4] != b"ADAT":
                failures["not ADAT"] += 1
                continue
            flags = struct.unpack_from("<H", blob, 6)[0]
            count = struct.unpack_from("<I", blob, 8)[0]
            total["containers"] += 1
            by_flags[flags]["containers"] += 1
            if count == 0:
                continue
            for slot in range(args.per_container):
                index = (slot * count) // args.per_container
                try:
                    info = stream_info(blob, index)
                except (SystemExit, ValueError) as error:
                    failures[f"info: {type(error).__name__}"] += 1
                    continue
                if info["codec"] != 0x0B:
                    failures[f"codec 0x{info['codec']:02x}"] += 1
                    continue
                payload = info["payload"]
                payload = payload[: len(payload) - (len(payload) % BLOCK_BYTES)]
                if not payload:
                    failures["empty payload"] += 1
                    continue
                try:
                    pcm, channels, counts, packets, _last, _first = decode_packets(
                        lib, payload, 48000)
                except Exception as error:  # noqa: BLE001 - the point is the reason
                    failures[f"{type(error).__name__}: {str(error)[:40]}"] += 1
                    continue
                seconds = counts[-1] / 48000
                level = rms(pcm)
                durations.append(seconds)
                loudness.append(level)
                if level < 100:
                    silence += 1
                total["streams"] += 1
                total["seconds"] += seconds
                by_flags[flags]["streams"] += 1
                by_flags[flags]["seconds"] += seconds
                records.append((start, index, flags, channels, info["rate"],
                                info["samples"], counts[-1], level))

    print(f"containers sampled {total['containers']}  streams decoded {total['streams']}")
    print(f"  audio {total['seconds'] / 60:.1f} minutes  silence (<100 rms) {silence}")
    if durations:
        durations.sort()
        print(f"  duration s: min {durations[0]:.2f} median "
              f"{durations[len(durations) // 2]:.2f} max {durations[-1]:.2f}")
    if loudness:
        loudness.sort()
        print(f"  rms: median {loudness[len(loudness) // 2]:.0f} "
              f"max {loudness[-1]:.0f}")
    print("  by variant:")
    for flags, counter in sorted(by_flags.items(), key=lambda item: -item[1]["streams"]):
        streams = counter["streams"]
        minutes = counter["seconds"] / 60
        print(f"    0x{flags:04x}: {counter['containers']} containers, "
              f"{streams} streams, {minutes:.1f} min")
    if failures:
        print("  failures:")
        for reason, count in failures.most_common(6):
            print(f"    {count:4d}  {reason}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as handle:
            handle.write("container\tstream\tflags\tchannels\tdeclared_rate\t"
                         "declared_samples\tdecoded_samples\trms\n")
            for record in records:
                handle.write(f"0x{record[0]:x}\t{record[1]}\t0x{record[2]:04x}\t"
                             f"{record[3]}\t{record[4]}\t{record[5]}\t{record[6]}\t"
                             f"{record[7]:.0f}\n")
        print(f"  wrote {args.out}")
    return 0 if total["streams"] else 1


if __name__ == "__main__":
    sys.exit(main())
