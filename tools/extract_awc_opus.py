#!/usr/bin/env python3
"""Export all AWC codec 0x0B streams as untrimmed 48 kHz PCM WAV.

Each 0x800-byte data block is `[u16le size][size-byte Opus packet]` with zero
padding.  The output is always 48 kHz (the Opus decoder clock); the AWC source
rate is recorded in the manifest.  Seek mismatches and encoded silence are
preserved and flagged, not discarded.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_awc_opus_probe import RATE, decode_packets, load_opus, streams  # noqa: E402

DEFAULT_FRAMING = Path("handoff/audio-awc-framing.tsv")
DEFAULT_OUT = Path("output/extracted/audio-opus")


def unique_paths(framing: Path, codec: str):
    seen = set()
    for row in csv.DictReader(framing.open(), delimiter="\t"):
        if row.get("codec") == codec and not row.get("error"):
            path = row["path"]
            if path not in seen:
                seen.add(path)
                yield path


def seek_state(counts, last, seek, channels):
    if len(seek) % 4:
        return "malformed"
    expected = list(struct.unpack(f"<{len(seek) // 4}I", seek))
    if not expected:
        return "missing"
    for scale in dict.fromkeys((1, channels)):
        if [count * scale for count in counts[:-1]] == expected[:-1]:
            return "terminal_ok" if last * scale == expected[-1] else "terminal_mismatch"
    return "mismatch"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--framing", type=Path, default=DEFAULT_FRAMING)
    ap.add_argument("--codec", default="0x0b")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    paths = list(unique_paths(args.framing, args.codec))
    if args.limit:
        paths = paths[: args.limit]
    print(f"{len(paths)} containers with codec {args.codec}")
    lib = load_opus()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = []

    for i, path in enumerate(paths, 1):
        digest = hashlib.sha1(path.encode()).hexdigest()[:8]
        target = args.out / f"{Path(path).stem}-{digest}"
        try:
            rows = list(streams(Path(path)))
        except Exception as exc:
            manifest.append({"path": path, "error": f"parse: {exc}"})
            print(f"{i}/{len(paths)} PARSE FAIL {path}: {exc}")
            continue
        for stream, codec, sub_id, rate, declared, offset, payload, seek in rows:
            if codec != int(args.codec, 16):
                continue
            try:
                pcm, channels, counts, packets, last, first = decode_packets(lib, payload)
                state = seek_state(counts, last, seek, channels)
                row = {
                    "path": path,
                    "stream": stream,
                    "sub_id": f"0x{sub_id:02x}",
                    "source_rate": rate,
                    "output_rate": RATE,
                    "declared_samples": declared,
                    "data_offset": f"0x{offset:x}",
                    "data_bytes": len(payload),
                    "packets": packets,
                    "decoded_frames": counts[-1],
                    "channels": channels,
                    "seek": state,
                    "silent": "yes" if not any(pcm) else "no",
                }
                if not args.verify_only:
                    target.mkdir(parents=True, exist_ok=True)
                    wav = target / f"stream-{stream:02d}.wav"
                    with wave.open(str(wav), "wb") as out:
                        out.setnchannels(channels)
                        out.setsampwidth(2)
                        out.setframerate(RATE)
                        out.writeframes(pcm)
                    row.update({
                        "output": str(wav),
                        "bytes": wav.stat().st_size,
                        "sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
                    })
                manifest.append(row)
            except Exception as exc:
                manifest.append({"path": path, "stream": stream, "error": str(exc)})
                print(f"{i}/{len(paths)} FAIL {path} stream {stream}: {exc}")
        if i % 100 == 0:
            print(f"{i}/{len(paths)} containers")

    out_manifest = args.out / "manifest.tsv"
    fields = ["path", "stream", "sub_id", "source_rate", "output_rate",
              "declared_samples", "data_offset", "data_bytes", "packets",
              "decoded_frames", "channels", "seek", "silent",
              "output", "bytes", "sha256", "error"]
    with out_manifest.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t",
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest)
    ok = sum(not row.get("error") for row in manifest)
    print(f"wrote {out_manifest}: {ok} streams, {len(manifest) - ok} errors")


if __name__ == "__main__":
    main()
