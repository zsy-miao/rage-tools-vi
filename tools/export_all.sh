#!/usr/bin/env bash
# Rebuild the canonical large-archive output set from a GTA VI source tree.
# Usage: tools/export_all.sh SOURCE_ROOT [OUTPUT_ROOT]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:?usage: export_all.sh SOURCE_ROOT [OUTPUT_ROOT]}"
OUT="${2:-$ROOT/output}"
WORKERS="${WORKERS:-16}"
cd "$ROOT"

declare -A ARCHIVE=(
  [anim]="$SRC/anim.rpf"
  [packs]="$SRC/packs.rpf"
  [navmeshes]="$SRC/navmeshes.rpf"
  [core_bvh4]="$SRC/pack/core_bvh4/core_bvh4.rpf"
  [story000]="$SRC/pack/story000/story000.rpf"
  [audio]="$SRC/audio.rpf"
  [movies]="$SRC/movies.rpf"
  [levels]="$SRC/levels.rpf"
)

mkdir -p "$OUT/index" "$OUT/extracted"
: > "$OUT/verification.tsv"

for name in anim packs navmeshes core_bvh4 story000 audio movies levels; do
  src="${ARCHIVE[$name]}"
  [[ -f "$src" ]] || { echo "missing $src" >&2; exit 1; }
  echo "== index $name: $src"
  python3 tools/stream_index.py "$src" --out "$OUT/index/$name.tsv"
done

# Extract the archives that were part of the verified output set. movies and
# levels are indexed only: levels decodes to ~175 GB and would not fit.
for name in anim packs navmeshes core_bvh4 story000 audio; do
  src="${ARCHIVE[$name]}"
  echo "== extract $name"
  python3 tools/bulk_extract.py "$src" "$OUT/index/$name.tsv" "$OUT/extracted/$name" \
    --workers "$WORKERS" --manifest "$OUT/extracted/$name/manifest.tsv"
  python3 tools/verify_bulk.py "$src" "$OUT/index/$name.tsv" \
    "$OUT/extracted/$name/manifest.tsv" --out "$OUT/verification.tsv"
done

# audio.rpf also carries ADAT AWC containers and the decoded XMA2 subset.
PYTHON="${PYTHON:-python3}" "$ROOT/tools/rebuild_audio.sh" "$SRC/audio.rpf" "$OUT/extracted"

echo "== done"
cat "$OUT/verification.tsv"
du -sh "$OUT/index" "$OUT/extracted"
