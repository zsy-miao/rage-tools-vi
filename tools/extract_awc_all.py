"""Decode every `ADAT` stream in a framing table: Opus to WAV, XMA2 via ffmpeg.

The container parse is `tools/awc_parse.py`, which follows the published layout
(Leonida's `awc_opus.py` and the GTA6-Asset-Info notes). This tool adds only the
bookkeeping: which streams a table lists, what came out, and the check that makes
the result trustworthy — `frames * channels / declared`, which must sit at or just
above 1.0 because the declared count is interleaved across channels.

    python3 tools/extract_awc_all.py --framing handoff/audio-awc-framing.tsv \\
        --out-manifest handoff/audio-full.tsv --no-wav
"""
import argparse
import csv
import hashlib
import struct
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import awc_parse  # noqa: E402
from data_awc_opus_probe import decode_packets, load_opus  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--framing", type=Path, action="append", required=True)
    parser.add_argument("--out-manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("cache/awc-out"))
    parser.add_argument("--no-wav", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    rows, seen = [], set()
    for path in args.framing:
        for row in csv.DictReader(path.open(), delimiter="\t"):
            if row["path"] in seen:
                continue
            seen.add(row["path"])
            rows.append(row)
    if args.limit:
        rows = rows[:args.limit]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    lib = load_opus()
    stats = {"opus": 0, "xma2": 0, "other": 0, "error": 0}
    with args.out_manifest.open("w") as out:
        writer = csv.writer(out, delimiter="\t", lineterminator="\n")
        writer.writerow(["container", "stream", "codec", "channels", "frames",
                         "declared", "rate", "ratio", "path", "sha256"])
        for row in rows:
            source = Path(row["path"])
            if not source.is_file():
                stats["error"] += 1
                continue
            data = source.read_bytes()
            try:
                streams, _ = awc_parse.parse(data)
            except ValueError:
                stats["error"] += 1
                continue
            for index, stream in enumerate(streams):
                offset, size = stream["data"]
                payload = data[offset:offset + size]
                declared = stream["samples"]
                channels = stream["channels"] or 1
                rate = stream["rate"] or 48000
                digest = ""
                if stream["codec"] == 0x0B:
                    packages = awc_parse.opus_packets(data, offset, size)
                    if not packages:
                        stats["error"] += 1
                        continue
                    try:
                        pcm, pch, _, _, _, _ = decode_packets(lib, payload)
                    except Exception:
                        stats["error"] += 1
                        continue
                    channels = pch or channels
                    frames = len(pcm) // (2 * max(1, channels))
                    stats["opus"] += 1
                elif stream["codec"] == 0x05:
                    if args.no_wav:
                        frames = 0
                        stats["xma2"] += 1
                    else:
                        from test_awc_xma2 import wav_xma2   # needs numpy
                        src = args.out_dir / f"{source.stem}-{index:03d}.xma2.wav"
                        src.write_bytes(wav_xma2(payload, declared, rate,
                                                 channels=channels))
                        dst = src.with_suffix(".wav")
                        run = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error",
                                              "-y", "-i", str(src),
                                              "-c:a", "pcm_s16le", str(dst)],
                                             capture_output=True, text=True)
                        src.unlink(missing_ok=True)
                        if run.returncode or not dst.exists():
                            stats["error"] += 1
                            continue
                        frames = 0
                        digest = hashlib.sha256(dst.read_bytes()).hexdigest()
                        stats["xma2"] += 1
                else:
                    stats["other"] += 1
                    continue
                ratio = (frames * channels / declared) if declared else 0.0
                target = ""
                if not args.no_wav and stream["codec"] == 0x0B:
                    target = args.out_dir / f"{source.stem}-{index:03d}.wav"
                    with wave.open(str(target), "wb") as handle:
                        handle.setnchannels(channels)
                        handle.setsampwidth(2)
                        handle.setframerate(rate)
                        handle.writeframes(pcm)
                    digest = hashlib.sha256(Path(target).read_bytes()).hexdigest()
                writer.writerow([source.name, index, f"0x{stream['codec']:02x}",
                                 channels, frames, declared, rate,
                                 f"{ratio:.4f}", target, digest])
                out.flush()
    print("decoded:", stats, "->", args.out_manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
