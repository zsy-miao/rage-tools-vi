"""Decode the `0xff21` / `0xff61` ADAT variants to WAV.

Same 8-byte chunk records as `0xff02` and the same `0x55` payload layout (0x800
blocks of `[u16 size][packet]`), but the table is not at a computable offset: it
is the longest 8-byte-aligned suffix before `data_offset` whose records parse.
Streams are paired by type order — the i-th `0x76` descriptor belongs to the i-th
`0x55` data chunk — because the optional chunks make per-stream grouping by
position unreliable.

    python3 tools/extract_awc_variants.py --manifest handoff/audio-awc-framing.tsv \\
        --out-dir output/extracted/audio-variants --limit 4
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

KNOWN = {0x55, 0x36, 0x76, 0xA3, 0xFA, 0x48, 0x5C, 0x68, 0x2B, 0x5A, 0xD9, 0xBD}


def find_table(data):
    streams, data_offset = struct.unpack_from("<II", data, 0x08)
    if not streams or not (16 < data_offset <= len(data)):
        return None
    best = None
    for start in range(16, data_offset):
        if (data_offset - start) % 8:
            continue
        chunks = []
        for position in range(start, data_offset, 8):
            raw = struct.unpack_from("<Q", data, position)[0]
            kind = raw >> 56
            size = (raw >> 28) & 0x0FFFFFFF
            offset = raw & 0x0FFFFFFF
            if kind not in KNOWN or not size or offset + size > len(data):
                chunks = []
                break
            chunks.append((kind, size, offset))
        if chunks and (best is None or len(chunks) > len(best)):
            best = chunks
    return streams, data_offset, best


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--out-manifest", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--no-wav", action="store_true",
                        help="measure only; skip writing audio")
    args = parser.parse_args()

    rows = [r for r in csv.DictReader(args.manifest.open(), delimiter="\t")
            if r["flags"] in ("0xff21", "0xff61") and r["codec"] == "0x0b"]
    seen = set()
    unique = []
    for row in rows:
        if row["path"] in seen:
            continue
        seen.add(row["path"])
        unique.append(row)
    if args.limit:
        unique = unique[:args.limit]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_manifest = args.out_manifest or (args.out_dir / "manifest.tsv")
    lib = load_opus()
    written = failed = 0
    with out_manifest.open("w") as out:
        writer = csv.writer(out, delimiter="\t", lineterminator="\n")
        writer.writerow(["container", "stream", "packets", "channels", "frames",
                         "declared", "rate", "path", "sha256"])
        for row in unique:
            source = Path(row["path"])
            if not source.is_file():
                failed += 1
                continue
            data = source.read_bytes()
            found = find_table(data)
            if not found:
                failed += 1
                continue
            streams, _, chunks = found
            descriptors = [c for c in chunks if c[0] == 0x76]
            payloads = [c for c in chunks if c[0] == 0x55]
            for stream, payload_chunk in enumerate(payloads):
                _, size, offset = descriptors[stream]
                _, dsize, doff = payload_chunk
                body = data[offset:offset + size]
                if len(body) < 0x20:
                    failed += 1
                    continue
                rate = struct.unpack_from("<H", body, 0x08)[0]
                declared = struct.unpack_from("<I", body, 0x00)[0]
                if body[0x1C] != 0x0B:
                    failed += 1
                    continue
                payload = data[doff:doff + dsize]
                if not payload or len(payload) % 0x800:
                    failed += 1
                    continue
                try:
                    pcm, channels, counts, packets, _, _ = decode_packets(lib, payload)
                except Exception:
                    failed += 1
                    continue
                frames = len(pcm) // (2 * channels)
                target, digest = "", ""
                if not args.no_wav:
                    target = args.out_dir / f"{source.stem}-{stream:03d}.wav"
                    with wave.open(str(target), "wb") as handle:
                        handle.setnchannels(channels)
                        handle.setsampwidth(2)
                        handle.setframerate(rate)
                        handle.writeframes(pcm)
                    digest = hashlib.sha256(target.read_bytes()).hexdigest()
                written += 1
                writer.writerow([source.name, stream, packets, channels,
                                 frames, declared, rate, target, digest])
    print(f"wrote {written} WAVs, {failed} failures -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
