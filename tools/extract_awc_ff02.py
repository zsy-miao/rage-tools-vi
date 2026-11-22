"""Decode the `0xff02` AWC variant to WAV (story000 cutscene audio).

Header: `ADAT`, version 1, flags `0xff02`, stream count, data offset, then
`4 * streams` bytes and an 8-byte chunk table ending at the data offset:

    record = offset:28 | size:28 | type:8   (little-endian u64)

Every stream owns seven chunks in order `0x36 0x55 0x5c 0x76 0xa3 0xb2 0xbd`.
`0x55` is the Opus data, a multiple of 0x800 blocks of `[u16 size][packet]`
entries with zero padding; `0x76` is the 32-byte descriptor (declared sample
count at `+0x00`/`+0x0c`, rate as the low u16 at `+0x08`, codec at `+0x1c`).

Decoding reuses the libopus walker from the `audio.rpf` work, so the only new
part is header parsing. `--limit` keeps a control run small; output sizes are
reported so a bulk run can be planned against the disk budget.
"""

import argparse
import csv
import hashlib
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_awc_opus_probe import decode_packets, load_opus  # noqa: E402

TYPES = (0x36, 0x55, 0x5C, 0x76, 0xA3, 0xB2, 0xBD)


def parse(data):
    streams, data_offset = struct.unpack_from("<II", data, 0x08)
    table = 0x10 + 4 * streams
    count = (data_offset - table) // 8
    chunks = []
    for index in range(count):
        value = struct.unpack_from("<Q", data, table + 8 * index)[0]
        chunks.append(((value >> 56) & 0xFF,
                       (value >> 28) & 0x0FFFFFFF,
                       value & 0x0FFFFFFF))
    return streams, data_offset, chunks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out-manifest", type=Path, default=None)
    args = parser.parse_args()

    rows = list(csv.DictReader(args.manifest.open(), delimiter="\t"))
    if args.limit:
        rows = rows[: args.limit]
    lib = load_opus()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_manifest = args.out_manifest or (args.out_dir / "manifest.tsv")

    written = 0
    bytes_out = 0
    failed = 0
    with out_manifest.open("w") as out:
        writer = csv.writer(out, delimiter="\t", lineterminator="\n")
        writer.writerow(["container", "stream", "streams", "packets", "channels",
                         "frames", "declared", "rate", "path", "sha256"])
        for row in rows:
            source = Path(row["path"])
            data = source.read_bytes()
            if struct.unpack_from("<H", data, 6)[0] != 0xFF02:
                continue
            streams, _, chunks = parse(data)
            if len(chunks) != streams * len(TYPES):
                failed += 1
                continue
            for stream in range(streams):
                group = chunks[stream * len(TYPES):(stream + 1) * len(TYPES)]
                by_type = {chunk[0]: chunk for chunk in group}
                if 0x55 not in by_type or 0x76 not in by_type:
                    failed += 1
                    continue
                _, size, off = by_type[0x76]
                body = data[off:off + size]
                if len(body) < 0x20:
                    failed += 1
                    continue
                rate = struct.unpack_from("<H", body, 0x08)[0]
                declared = struct.unpack_from("<I", body, 0x00)[0]
                codec = body[0x1C]
                if codec != 0x0B:
                    failed += 1
                    continue
                _, dsize, doff = by_type[0x55]
                payload = data[doff:doff + dsize]
                if not payload or len(payload) % 0x800:
                    failed += 1
                    continue
                try:
                    pcm, channels, counts, packets, _, _ = decode_packets(lib, payload)
                except Exception:
                    failed += 1
                    continue
                name = f"{source.stem}-{stream:03d}.wav"
                target = args.out_dir / name
                with wave.open(str(target), "wb") as handle:
                    handle.setnchannels(channels)
                    handle.setsampwidth(2)
                    handle.setframerate(rate)
                    handle.writeframes(pcm)
                digest = hashlib.sha256(target.read_bytes()).hexdigest()
                bytes_out += target.stat().st_size
                written += 1
                writer.writerow([source.name, stream, streams, packets, channels,
                                 len(pcm) // (2 * channels), declared, rate,
                                 target, digest])
            out.flush()

    print(f"decoded {written} streams from {min(len(rows), args.limit or len(rows))} containers, "
          f"{bytes_out:,} bytes written, {failed} failures")
    print(f"manifest {out_manifest}")


if __name__ == "__main__":
    main()
