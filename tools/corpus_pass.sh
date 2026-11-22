#!/usr/bin/env bash
# One pass over every archive: index, entry model, entries.
#
#   tools/corpus_pass.sh [SOURCE_DIR] [--entries]
#
# SOURCE_DIR defaults to the local NVMe copy of the game directory. For each
# `*.rpf` it
#   1. writes output/index/<name>.tsv when missing,
#   2. fits the entry model per pack (tools/pack_model_fit.py),
#   3. with --entries, emits a payload-derived entry manifest for the unit the
#      archive's stream/declared ratio implies (tools/pair_entry_manifest.py).
#
# Results land in handoff/corpus-pass/<name>.tsv and are summarised in
# handoff/corpus-pass.tsv.
set -uo pipefail
cd "$(dirname "$0")/.."
SRC=${1:-/home/lynxnathan/gta6-source}
entries=0
[ "${2:-}" = "--entries" ] && entries=1
out=handoff/corpus-pass
mkdir -p "$out" output/index

printf 'archive\tranges\tzlib\tstored_bytes\tpacks\texact_packs\tunit\tentries\n' > handoff/corpus-pass.tsv
for path in $(find "$SRC" -name '*.rpf' | sort); do
    name=$(basename "$path" .rpf)
    index="output/index/$name.tsv"
    if [ ! -f "$index" ]; then
        python3 tools/stream_index.py "$path" --out "$index" >/dev/null 2>&1
    fi
    [ -f "$index" ] || { echo "$name: no index" >&2; continue; }

    ranges=$(awk 'END{print NR-1}' "$index")
    zlib=$(awk -F'\t' 'NR>1 && $1=="zlib"' "$index" | wc -l)
    stored=$(awk -F'\t' 'NR>1{s+=$4} END{printf "%d", s}' "$index")
    declared=$(awk -F'\t' -v a="$name.rpf" '$1==a{s+=$5} END{printf "%d", s}' \
        handoff/header-census-full.tsv 2>/dev/null)
    unit=""
    if [ -n "$declared" ] && [ "$declared" -gt 0 ]; then
        ratio=$(python3 -c "print(f'{$zlib/$declared:.2f}')")
        unit=$(python3 -c "
r=$ratio
print('pairs' if 1.6 <= r <= 2.4 else 'single' if abs(r-1) < 0.08 else ('chains' if r > 1 else ''))")
    fi

    if [ -f "handoff/pack-model-fit.tsv" ]; then
        python3 tools/pack_model_fit.py --archive "$path" --index "$index" \
            --out "$out/pack-model-$name.tsv" >/dev/null 2>&1
        packs=$(awk 'END{print NR-1}' "$out/pack-model-$name.tsv" 2>/dev/null)
        exact=$(awk -F'\t' 'NR>1 && $7!="-"' "$out/pack-model-$name.tsv" 2>/dev/null | wc -l)
    else
        packs=""; exact=""
    fi

    emitted=""
    if [ "$entries" = 1 ]; then
        python3 tools/pair_entry_manifest.py --archive "$path" --index "$index" \
            --unit "$unit" --out "$out/entries-$name.tsv" --tolerance 0 \
            >/dev/null 2>&1 && emitted=$(awk 'END{print NR-1}' "$out/entries-$name.tsv" 2>/dev/null)
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
        "$name.rpf" "$ranges" "$zlib" "$stored" "${packs:-}" "${exact:-}" "$unit" "${emitted:-}" \
        >> handoff/corpus-pass.tsv
    printf '%-28s %8s ranges %8s zlib  %s/%s packs  unit=%s\n' \
        "$name.rpf" "$ranges" "$zlib" "${exact:-?}" "${packs:-?}" "$unit"
done
echo
echo "summary -> handoff/corpus-pass.tsv"
