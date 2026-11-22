#!/usr/bin/env python3
"""Decode AWC streams whose 0x76 codec is XMA2 (observed codec 0x05).

The GTA VI container uses a new ADAT header, but its 32-bit XMA2 payloads are
accepted by ffmpeg once wrapped in a real XMA2WAVEFORMATEX RIFF file.  This tool
selects streams from handoff/audio-awc-framing.tsv, wraps the 0x55 data chunk,
and writes PCM WAV plus a manifest with SHA-256.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.test_awc_xma2 import parse_awc, wav_xma2

DEFAULT_FRAMING = Path("handoff/audio-awc-framing.tsv")
DEFAULT_OUT = Path("output/extracted/audio-xma2")


def decode_one(path: str, stream: int, out_dir: Path, channels: int = 1):
    streams = parse_awc(path)
    if stream >= len(streams):
        return None
    data, num_samples, rate = streams[stream]
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{Path(path).stem}-{hashlib.sha1(path.encode()).hexdigest()[:8]}-s{stream}"
    src = out_dir / f"{stem}.xma2.wav"
    dst = out_dir / f"{stem}.wav"
    src.write_bytes(wav_xma2(data, num_samples, rate, channels=channels))
    run = subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "error", "-y", "-i", str(src),
         "-c:a", "pcm_s16le", str(dst)],
        capture_output=True, text=True,
    )
    src.unlink(missing_ok=True)
    if run.returncode != 0 or not dst.exists():
        dst.unlink(missing_ok=True)
        return {"error": run.stderr.strip().splitlines()[:2]}
    return {
        "output": str(dst),
        "bytes": dst.stat().st_size,
        "sha256": hashlib.sha256(dst.read_bytes()).hexdigest(),
        "rate": rate,
        "samples": num_samples,
        "data_bytes": len(data),
        "channels": channels,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--framing", type=Path, default=DEFAULT_FRAMING)
    ap.add_argument("--codec", default="0x05")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--channels", type=int, choices=(1, 2), default=1)
    args = ap.parse_args()

    rows = [
        r for r in csv.DictReader(args.framing.open(), delimiter="\t")
        if r.get("codec") == args.codec and not r.get("error")
    ]
    if args.limit:
        rows = rows[: args.limit]
    print(f"{len(rows)} streams with codec {args.codec}")

    manifest = []
    for i, row in enumerate(rows, 1):
        result = decode_one(row["path"], int(row["stream"]), args.out, args.channels)
        item = {
            "path": row["path"],
            "stream": row["stream"],
            "codec": row["codec"],
            "rate": row["rate"],
            "data_size": row["data_size"],
        }
        if result:
            item.update(result)
        else:
            item["error"] = "stream missing from parsed AWC"
        manifest.append(item)
        if result and "error" not in result:
            print(f"{i}/{len(rows)} OK {result['output']} {result['bytes']} bytes")
        else:
            print(f"{i}/{len(rows)} FAIL {row['path']} stream {row['stream']}: {result}")

    out_manifest = args.out / "manifest.tsv"
    out_manifest.parent.mkdir(parents=True, exist_ok=True)
    fields = ["path", "stream", "codec", "rate", "samples", "channels",
              "data_size", "data_bytes", "output", "bytes", "sha256", "error"]
    with out_manifest.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest)
    print(f"wrote {out_manifest}")


if __name__ == "__main__":
    sys.exit(main())
