#!/usr/bin/env python3
"""Export AWC codec 0x02 ACE1 impulse responses as float32 WAV."""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_awc_ace1_ir as ace  # noqa: E402
from data_awc_opus_probe import stream_chunks  # noqa: E402
from data_awc_trim_controls import parse_ace1  # noqa: E402

DEFAULT_FRAMING = Path("handoff/audio-awc-framing.tsv")
DEFAULT_OUT = Path("output/extracted/audio-ace1")


def containers(framing: Path, codec: str):
    seen = set()
    for row in csv.DictReader(framing.open(), delimiter="\t"):
        if row.get("codec") == codec and not row.get("error"):
            path = row["path"]
            if path not in seen:
                seen.add(path)
                yield path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--framing", type=Path, default=DEFAULT_FRAMING)
    ap.add_argument("--codec", default="0x02")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    paths = list(containers(args.framing, args.codec))
    if args.limit:
        paths = paths[: args.limit]
    print(f"{len(paths)} containers with codec {args.codec}")
    args.out.mkdir(parents=True, exist_ok=True)
    transform = ace.InverseFFT()
    manifest = []
    try:
        for i, path in enumerate(paths, 1):
            digest = hashlib.sha1(path.encode()).hexdigest()[:8]
            target = args.out / f"{Path(path).stem}-{digest}"
            try:
                for index, chunks in stream_chunks(Path(path)):
                    if 0x55 not in chunks or 0x76 not in chunks:
                        continue
                    _, fmt = chunks[0x76]
                    if fmt[0x1C] != int(args.codec, 16):
                        continue
                    offset, payload = chunks[0x55]
                    allocated = int.from_bytes(fmt[0:4], "little")
                    rate = int.from_bytes(fmt[8:10], "little")
                    taps = int.from_bytes(fmt[0x0C:0x10], "little")
                    floats, _, _ = parse_ace1(payload, allocated)
                    impulse, blocks, levels = ace.reconstruct(floats, taps, transform)
                    row = {
                        "path": path,
                        "stream": index,
                        "rate": rate,
                        "declared_taps": taps,
                        "data_offset": f"0x{offset:x}",
                        "data_bytes": len(payload),
                        "nonzero_blocks": blocks,
                        "inside_rms": f"{levels[0]:.7g}",
                        "after_rms": f"{levels[1]:.7g}",
                        "overlap_rms": f"{levels[2]:.7g}",
                    }
                    if not args.verify_only:
                        target.mkdir(parents=True, exist_ok=True)
                        wav = target / f"stream-{index:02d}.wav"
                        ace.write_float_wav(wav, rate, impulse)
                        row.update({
                            "output": str(wav),
                            "bytes": wav.stat().st_size,
                            "sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
                        })
                    manifest.append(row)
            except Exception as exc:
                manifest.append({"path": path, "error": str(exc)})
                print(f"{i}/{len(paths)} FAIL {path}: {exc}")
            if i % 25 == 0:
                print(f"{i}/{len(paths)} containers")
    finally:
        transform.close()

    out_manifest = args.out / "manifest.tsv"
    fields = ["path", "stream", "rate", "declared_taps", "data_offset",
              "data_bytes", "nonzero_blocks", "inside_rms", "after_rms",
              "overlap_rms", "output", "bytes", "sha256", "error"]
    with out_manifest.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t",
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest)
    ok = sum(not row.get("error") for row in manifest)
    print(f"wrote {out_manifest}: {ok} streams, {len(manifest) - ok} errors")


if __name__ == "__main__":
    main()
