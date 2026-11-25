"""Find a 0xff25 payload by decoding candidates, not by guessing the container layout.

The structural route stalled: no chunk table under any shift, no size field, no block
framing. This takes the other direction — try candidate payload starts and packet
prefix widths, decode a few packets with libopus, and score the result by whether it
sounds like programme material (spectral flatness well below 1.0).

    python3 tools/probe_ff25_payload.py /src/audio.rpf --start 0x548f000 --end 0x548f000+266240
"""

import argparse
import math
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_awc_opus_probe import load_opus


def packets(blob, pos, want, width):
    out = []
    while len(out) < want:
        if width == 2:
            if pos + 2 > len(blob):
                break
            size = struct.unpack_from("<H", blob, pos)[0]
        else:
            if pos + 4 > len(blob):
                break
            size = struct.unpack_from("<I", blob, pos)[0]
        if not 1 <= size <= 1275 or pos + width + size > len(blob):
            break
        out.append(blob[pos + width:pos + width + size])
        pos += width + size
    return out


def flatness(pcm):
    import numpy as np
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
    if len(x) < 4096:
        return 1.0
    seg = x[: min(len(x), 48000)]
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) + 1e-12
    return float(np.exp(np.mean(np.log(spec))) / np.mean(spec))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--start", type=lambda v: int(v, 0), required=True)
    parser.add_argument("--end", type=lambda v: int(v, 0), required=True)
    parser.add_argument("--scan", type=lambda v: int(v, 0), default=0x2000, help="bytes to scan from the header end")
    parser.add_argument("--max-packets", type=lambda v: int(v, 0), default=40)
    args = parser.parse_args()

    import ctypes
    lib = load_opus()
    with args.archive.open("rb") as handle:
        handle.seek(args.start)
        blob = handle.read(args.end - args.start)

    results = []
    for width in (2, 4):
        for offset in range(0x40, min(args.scan, len(blob) - 8)):
            group = packets(blob, offset, args.max_packets, width)
            if len(group) < 8:
                continue
            error = ctypes.c_int()
            state = lib.opus_decoder_create(48000, 2, ctypes.byref(error))
            if not state or error.value:
                continue
            frame = (ctypes.c_int16 * (5760 * 2))()
            pcm = bytearray()
            ok = 0
            try:
                for packet in group:
                    got = lib.opus_decode(state, packet, len(packet), frame, 5760, 0)
                    if got <= 0:
                        break
                    pcm.extend(struct.pack(f"<{got * 2}h", *frame[: got * 2]))
                    ok += 1
            finally:
                lib.opus_decoder_destroy(state)
            if ok < 8:
                continue
            score = flatness(pcm)
            results.append((score, ok, width, offset, len(pcm)))

    if not results:
        print("no candidate decoded")
        return 1
    results.sort()
    print(f"{'flatness':>9s} {'packets':>8s} {'width':>6s} {'offset':>8s} {'pcm':>9s}")
    for score, ok, width, offset, size in results[:8]:
        print(f"{score:9.4f} {ok:8d} {width:6d} {offset:#8x} {size:9d}")
    print("\nlower flatness = more tonal (1.0 is white noise)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
