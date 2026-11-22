"""Decode one stream from an AWC container using the indexer's own table rules.

The existing probe expects the `0xff21` layout (data offset at `+0x0c`), so it yields
nothing on the `0xff02` pools that hold most of the corpus. This reads the chunk table
the way `tools/adat_index.py` verified it — four records per stream
(`0x36 0x55 0x76 0xa3`), table at `0x10 + 4*count` for `0xff02` or `0x50` for
`0xff21`, ending exactly at `header_size` — and then decodes the stream's Opus packets
with the libopus walker the project already uses.

    python3 tools/decode_adat_stream.py audio.rpf --start 0x16437000 --stream 0 \
        --output /tmp/stream.wav
    python3 tools/decode_adat_stream.py container.awc --stream 0 --output out.wav
"""

import argparse
import ctypes
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_awc_opus_probe import BLOCK_BYTES, decode_packets, load_opus, split_block

TABLE_AT = {0xFF21: lambda count: 0x50, 0xFF02: lambda count: 0x10 + 4 * count}

# Record types that appear in a real chunk table; used to locate the table of the
# variants whose position is not computable (0xff25, 0xff61).
KNOWN_TYPES = {0x55, 0x36, 0x76, 0xA3, 0xFA, 0x48, 0x5C, 0x68, 0x2B, 0x5A, 0xD9, 0xBD}


def scanned_table(blob, count, header_size):
    """Longest valid record run ending at `header_size`, for the scanned variants."""
    best = None
    limit = min(header_size, len(blob))
    for start in range(16, limit):
        if (header_size - start) % 8:
            continue
        ok = True
        for position in range(start, header_size, 8):
            (raw,) = struct.unpack_from("<Q", blob, position)
            kind = raw >> 56
            size = (raw >> 28) & 0x0FFFFFFF
            offset = raw & 0x0FFFFFFF
            if kind not in KNOWN_TYPES or size == 0 or offset + size > len(blob):
                ok = False
                break
        if ok:
            length = (header_size - start) // 8
            if best is None or length > best[1]:
                best = (start, length)
    if best is None:
        raise ValueError("no valid chunk table suffix")
    start, records = best
    if count == 0 or records % count:
        raise ValueError("table length is not a multiple of the stream count")
    return start, records // count


def records(blob, count, header_size, flags):
    """The chunk table as (kind, offset, size) triples."""
    start = TABLE_AT[flags](count) if flags in TABLE_AT else None
    if start is not None and count and (header_size - start) % (8 * count) == 0:
        per_stream = (header_size - start) // (8 * count)
    else:
        start, per_stream = scanned_table(blob, count, header_size)
    out = []
    for index in range(count * per_stream):
        (raw,) = struct.unpack_from("<Q", blob, start + 8 * index)
        out.append((raw >> 56, raw & 0x0FFFFFFF, (raw >> 28) & 0x0FFFFFFF))
    return out, per_stream


def stream_info(blob, index):
    version, flags, count, header_size = struct.unpack_from("<HHII", blob, 4)
    table, per_stream = records(blob, count, header_size, flags)
    if index >= count:
        raise SystemExit(f"stream {index} out of range (container has {count})")
    chunks = table[index * per_stream:(index + 1) * per_stream]
    data = next(((offset, size) for kind, offset, size in chunks if kind == 0x55), None)
    fmt = next(((offset, size) for kind, offset, size in chunks if kind == 0x76), None)
    if not data or not fmt:
        raise SystemExit("stream has no 0x55/0x76 pair")
    descriptor = blob[fmt[0]:fmt[0] + fmt[1]]
    samples = struct.unpack_from("<I", descriptor, 0)[0]
    rate = struct.unpack_from("<H", descriptor, 8)[0]
    codec, channels = descriptor[0x1C], descriptor[0x1D]
    frames = struct.unpack_from("<I", descriptor, 12)[0] if len(descriptor) >= 16 else 0
    payload = blob[data[0]:data[0] + data[1]]
    return {"flags": flags, "count": count, "rate": rate, "codec": codec,
            "channels": channels, "samples": samples, "frames": frames,
            "payload": payload, "per_stream": per_stream}


def ff25_packets(blob, first=0x860, block=0x800, payload=0x60):
    """Packets of a `0xff25` container: blocks of 0x800, payload at block+0x60.

    Derived from observation, not from a header field: every sampled container places
    packet runs at offsets congruent to 0x60 modulo 0x800, and each 0x800 block holds a
    fixed number of them. Stops at the first block whose run does not parse.
    """
    packets = []
    offset = first
    while offset < len(blob):
        position = offset
        run = []
        while position + 2 <= len(blob):
            size = struct.unpack_from("<H", blob, position)[0]
            if not 1 <= size <= 1275 or position + 2 + size > len(blob):
                break
            run.append(blob[position + 2:position + 2 + size])
            position += 2 + size
        if not run:
            break
        packets.extend(run)
        offset += block
    return packets


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("container", type=Path)
    parser.add_argument("--start", type=lambda v: int(v, 0), default=0,
                        help="offset inside an archive file (reads to --end)")
    parser.add_argument("--end", type=lambda v: int(v, 0), default=0)
    parser.add_argument("--stream", type=int, default=0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ff25", action="store_true",
                        help="decode the whole container as 0xff25 block-framed Opus")
    args = parser.parse_args()

    if args.start:
        if not args.end:
            sys.exit("--start needs --end")
        with args.container.open("rb") as handle:
            handle.seek(args.start)
            blob = handle.read(args.end - args.start)
    else:
        blob = args.container.read_bytes()
    if blob[:4] != b"ADAT":
        sys.exit("not an ADAT container")

    if args.ff25:
        packets = ff25_packets(blob)
        lib = load_opus()
        # Decode packet by packet: repacking into 0x800 blocks would split a packet that
        # straddles a boundary, which the block walker rejects.
        error = ctypes.c_int()
        state = lib.opus_decoder_create(48000, 2, ctypes.byref(error))
        if not state or error.value:
            raise SystemExit(f"opus_decoder_create failed: {error.value}")
        frame = (ctypes.c_int16 * (5760 * 2))()
        pcm = bytearray()
        channels = 2
        decoded = 0
        samples = 0
        try:
            for packet in packets:
                got = lib.opus_decode(state, packet, len(packet), frame, 5760, 0)
                if got <= 0:
                    break
                pcm.extend(struct.pack(f"<{got * 2}h", *frame[:got * 2]))
                samples += got
                decoded += 1
        finally:
            lib.opus_decoder_destroy(state)
        seconds = samples / 48000
        print(f"0xff25: {len(packets):,} packets, {decoded:,} decoded, "
              f"{len(pcm):,} B PCM, {channels} ch, {seconds:.2f} s")
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(args.output), "wb") as handle:
                handle.setnchannels(channels)
                handle.setsampwidth(2)
                handle.setframerate(48000)
                handle.writeframes(pcm)
            print(f"wrote {args.output}")
        return 0

    info = stream_info(blob, args.stream)
    print(f"container flags 0x{info['flags']:04x}  streams {info['count']}  "
          f"records/stream {info['per_stream']}")
    print(f"stream {args.stream}: codec 0x{info['codec']:02x}  channels {info['channels']}  "
          f"declared rate {info['rate']} (decoding at 48 kHz)  samples {info['samples']}  "
          f"frames {info['frames']}  payload {len(info['payload']):,} B")
    if info["codec"] != 0x0B:
        sys.exit(f"codec 0x{info['codec']:02x} is not Opus; this tool decodes Opus only")

    payload = info["payload"]
    usable = len(payload) - (len(payload) % BLOCK_BYTES)
    if usable != len(payload):
        payload = payload[:usable]
    packets = sum(len(split_block(payload[i:i + BLOCK_BYTES]))
                  for i in range(0, len(payload), BLOCK_BYTES))
    # Opus marks the *input* rate; libopus only ever produces 48 kHz, and asking it
    # for anything else fails with OPUS_BAD_ARG (observed: a 32000 Hz descriptor).
    lib = load_opus()
    pcm, channels, counts, decoded_packets, _last, _first = decode_packets(
        lib, payload, 48000)
    seconds = len(pcm) / (2 * channels) / 48000
    print(f"packets {packets:,} (decoded {decoded_packets:,})  {len(pcm):,} B PCM  "
          f"{channels} ch  {seconds:.2f} s  total {counts[-1]:,} samples")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(args.output), "wb") as handle:
            handle.setnchannels(channels)
            handle.setsampwidth(2)
            handle.setframerate(48000)
            handle.writeframes(pcm)
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
