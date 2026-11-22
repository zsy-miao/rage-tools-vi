#!/usr/bin/env python3
"""Test little-endian length-prefixed Opus in one GTA VI ADAT container."""

import argparse
import ctypes
from ctypes.util import find_library
import math
import mmap
from pathlib import Path
import struct
import wave

from awc_framing import find_chunks


BLOCK_BYTES = 0x800
RATE = 48000
MAX_FRAME = RATE * 120 // 1000


def stream_chunks(path):
    with path.open("rb") as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
        if data[:4] != b"ADAT":
            raise ValueError(f"not ADAT: {path}")
        count = struct.unpack_from("<H", data, 8)[0]
        start = struct.unpack_from("<I", data, 12)[0]
        directory = find_chunks(data, start)
        indexes = (*struct.unpack_from(f"<{count}H", data, 16), len(directory))
        for index, (first, last) in enumerate(zip(indexes, indexes[1:])):
            chunks = {kind: (offset, data[offset:offset + size]) for kind, size, offset in directory[first:last]}
            yield index, chunks


def streams(path):
    for index, chunks in stream_chunks(path):
        if 0x76 not in chunks or 0x55 not in chunks:
            continue
        _, fmt = chunks[0x76]
        offset, payload = chunks[0x55]
        seek = chunks.get(0xA3, (0, b""))[1]
        if len(fmt) < 32:
            continue
        samples = struct.unpack_from("<I", fmt)[0]
        rate = struct.unpack_from("<H", fmt, 8)[0]
        yield index, fmt[0x1C], fmt[0x1D], rate, samples, offset, payload, seek


def split_block(block):
    cursor = 0
    packets = []
    while cursor + 2 <= len(block):
        size = struct.unpack_from("<H", block, cursor)[0]
        if size == 0:
            break
        end = cursor + 2 + size
        if end > len(block):
            raise ValueError(f"packet length {size} at block +{cursor:#x} exceeds block")
        packets.append((cursor, block[cursor + 2:end]))
        cursor = end
    if any(block[cursor:]):
        raise ValueError(f"nonzero block padding at +{cursor:#x}")
    return packets


def load_opus():
    library = find_library("opus")
    if not library:
        raise RuntimeError("libopus is required")
    lib = ctypes.CDLL(library)
    lib.opus_decoder_create.argtypes = [ctypes.c_int32, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
    lib.opus_decoder_create.restype = ctypes.c_void_p
    lib.opus_decoder_destroy.argtypes = [ctypes.c_void_p]
    lib.opus_decoder_destroy.restype = None
    lib.opus_packet_get_nb_samples.argtypes = [ctypes.c_char_p, ctypes.c_int32, ctypes.c_int32]
    lib.opus_packet_get_nb_samples.restype = ctypes.c_int
    lib.opus_decode.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int16), ctypes.c_int, ctypes.c_int,
    ]
    lib.opus_decode.restype = ctypes.c_int
    return lib


def decode_packets(lib, payload, sample_rate=RATE):
    if not payload or len(payload) % BLOCK_BYTES:
        raise ValueError(f"invalid data length {len(payload)}")
    blocks = [
        split_block(payload[start:start + BLOCK_BYTES])
        for start in range(0, len(payload), BLOCK_BYTES)
    ]
    channels = max(1 + ((packet[0] >> 2) & 1) for block in blocks for _, packet in block)
    error = ctypes.c_int()
    state = lib.opus_decoder_create(sample_rate, channels, ctypes.byref(error))
    if not state or error.value:
        raise RuntimeError(f"opus_decoder_create failed: {error.value}")
    pcm = bytearray()
    counts = [0]
    packets = 0
    last_packet_start = 0
    frame = (ctypes.c_int16 * (MAX_FRAME * channels))()
    try:
        for block in blocks:
            count = counts[-1]
            for position, packet in block:
                last_packet_start = count
                expected = lib.opus_packet_get_nb_samples(packet, len(packet), sample_rate)
                decoded = lib.opus_decode(state, packet, len(packet), frame, MAX_FRAME, 0)
                if expected <= 0 or decoded != expected:
                    raise ValueError(f"packet +{position:#x}: expected {expected}, libopus returned {decoded}")
                count += decoded
                pcm.extend(struct.pack(f"<{decoded * channels}h", *frame[:decoded * channels]))
                packets += 1
            counts.append(count)
    finally:
        lib.opus_decoder_destroy(state)
    return pcm, channels, counts, packets, last_packet_start, blocks[0][0][1]


def decode_stream(lib, payload, seek, info, output):
    stream, sub_id, rate, declared, offset = info
    if rate != RATE or len(payload) % BLOCK_BYTES:
        raise ValueError(f"unsupported rate {rate} or data length {len(payload)}")
    pcm, channels, counts, packets, last_packet_start, first = decode_packets(lib, payload)
    expected_seek = list(struct.unpack(f"<{len(seek) // 4}I", seek)) if len(seek) % 4 == 0 else []
    scales = [scale for scale in {1, channels}
              if [count * scale for count in counts[:-1]] == expected_seek[:-1]]
    if not scales:
        raise ValueError(f"seek mismatch ({channels} channels): decoder {counts}; AWC {expected_seek}")
    if not any(pcm):
        raise ValueError("decoded audio is entirely silent")
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output / f"stream-{stream:02d}.wav"), "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)
            wav.setframerate(RATE)
            wav.writeframes(pcm)
    terminal_is_last_start = any(last_packet_start * scale == expected_seek[-1] for scale in scales)
    print(stream, hex(sub_id), hex(offset), len(payload), packets, len(first), hex(first[0]),
          ",".join(map(str, counts)), ",".join(map(str, expected_seek)), declared, channels,
          ",".join(str(scale) for scale in sorted(scales)), terminal_is_last_start, sep="\t")


def describe_float_stream(stream, rate, declared, offset, payload):
    if len(payload) != declared * 4:
        raise ValueError("0x02 extent is not four bytes per declared sample")
    values = [value for (value,) in struct.iter_unpack("<f", payload)]
    finite = sum(math.isfinite(value) for value in values)
    peak = max(abs(value) for value in values if math.isfinite(value))
    rms = math.sqrt(sum(value * value for value in values if math.isfinite(value)) / finite)
    invalid = [
        f"{index}:{payload[index * 4:index * 4 + 4].hex()}"
        for index, value in enumerate(values) if not math.isfinite(value)
    ]
    print(stream, hex(offset), rate, declared, finite, f"{peak:.5g}", f"{rms:.5g}",
          ",".join(invalid[:16]), sep="\t")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("awc", type=Path)
    parser.add_argument("--output", type=Path, help="write exact untrimmed PCM to WAV")
    parser.add_argument("--float-control", action="store_true", help="report 0x02 float32 statistics")
    args = parser.parse_args()
    if args.float_control:
        print("stream\tawc_data_offset\trate\tsamples\tfinite_floats\tpeak\trms\tnonfinite_words")
        for stream, codec, _, rate, declared, offset, payload, _ in streams(args.awc):
            if codec == 0x02:
                describe_float_stream(stream, rate, declared, offset, payload)
        return
    lib = load_opus()
    print("stream\tsub_id\tawc_data_offset\tbytes\tpackets\tpacket0_bytes\tpacket0_toc"
          "\tdecoded_boundaries\tseek_table\tdeclared_samples\tchannels\tseek_scales\tterminal_is_last_start")
    for stream, codec, sub_id, rate, declared, offset, payload, seek in streams(args.awc):
        if codec == 0x0B:
            decode_stream(lib, payload, seek, (stream, sub_id, rate, declared, offset), args.output)


if __name__ == "__main__":
    main()
