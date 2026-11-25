#!/usr/bin/env bash
# Rebuild every generated audio.rpf artifact from the source archive.
# Usage: PYTHON=/path/to/python tools/rebuild_audio.sh SOURCE_AUDIO_RPF [OUTPUT_EXTRACTED]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${1:?usage: rebuild_audio.sh SOURCE_AUDIO_RPF [OUTPUT_EXTRACTED]}"
OUT="${2:-$ROOT/output/extracted}"
PYTHON="${PYTHON:-python3}"
START="${START:-0x129b000}"
FRAMING="${FRAMING:-$OUT/audio-awc-framing.tsv}"

[[ -f "$SOURCE" ]] || { echo "missing source: $SOURCE" >&2; exit 1; }
END="$(stat -c %s "$SOURCE")"
cd "$ROOT"

rm -rf "$OUT/audio-awc" "$OUT/audio-xma2" "$OUT/audio-opus" "$OUT/audio-ace1"
mkdir -p "$OUT/audio-awc" "$OUT/audio-xma2" "$OUT/audio-opus" "$OUT/audio-ace1"

python3 tools/extract_awc.py "$SOURCE" \
  --start "$START" --end "$END" \
  --out-dir "$OUT/audio-awc" \
  --manifest "$OUT/audio-awc/manifest.tsv"

python3 tools/awc_framing.py --manifest "$OUT/audio-awc/manifest.tsv" --out "$FRAMING" --limit 0

"$PYTHON" tools/extract_awc_xma2.py --framing "$FRAMING" --limit 0 --out "$OUT/audio-xma2"
"$PYTHON" tools/extract_awc_opus.py --framing "$FRAMING" --limit 0 --out "$OUT/audio-opus"
"$PYTHON" tools/extract_awc_ace1.py --framing "$FRAMING" --limit 0 --out "$OUT/audio-ace1"

python3 - "$OUT" <<'PY'
import csv
import sys
from pathlib import Path

out = Path(sys.argv[1])
awc = list(csv.DictReader((out / "audio-awc" / "manifest.tsv").open(), delimiter="\t"))
xma2 = list(csv.DictReader((out / "audio-xma2" / "manifest.tsv").open(), delimiter="\t"))
opus = list(csv.DictReader((out / "audio-opus" / "manifest.tsv").open(), delimiter="\t"))
ace1 = list(csv.DictReader((out / "audio-ace1" / "manifest.tsv").open(), delimiter="\t"))
xma2_wavs = list((out / "audio-xma2").glob("*.wav"))
opus_wavs = list((out / "audio-opus").rglob("*.wav"))
ace1_wavs = list((out / "audio-ace1").rglob("*.wav"))
print(f"awc={len(awc)} xma2_ok={sum(not r.get('error') for r in xma2)} xma2_wavs={len(xma2_wavs)} "
      f"opus_ok={sum(not r.get('error') for r in opus)} opus_wavs={len(opus_wavs)} "
      f"ace1_ok={sum(not r.get('error') for r in ace1)} ace1_wavs={len(ace1_wavs)}")
if len(awc) != 6625:
    raise SystemExit(f"unexpected AWC count: {len(awc)}")
if len(xma2_wavs) != 151:
    raise SystemExit(f"unexpected XMA2 WAV count: {len(xma2_wavs)}")
if len(opus_wavs) != 2081:
    raise SystemExit(f"unexpected Opus WAV count: {len(opus_wavs)}")
if len(ace1_wavs) != 73:
    raise SystemExit(f"unexpected ACE1 WAV count: {len(ace1_wavs)}")
PY
