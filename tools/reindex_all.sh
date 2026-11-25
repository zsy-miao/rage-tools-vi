#!/usr/bin/env bash
# Re-run the stream index for every archive and check that each index still
# tiles its file exactly.  Writes output/index/<name>.tsv.
set -uo pipefail
cd "$(dirname "$0")/.."
SRC=${SRC:-/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK}
mkdir -p output/index
printf '%-30s %10s %10s %10s %8s\n' archive ranges stored MB chains
for path in $(find "$SRC" -name '*.rpf' | sort); do
    name=$(basename "$path" .rpf)
    out="output/index/$name.tsv"
    line=$(python3 tools/stream_index.py "$path" --out "$out" 2>&1 | tail -1)
    ranges=$(awk 'END{print NR-1}' "$out")
    stored=$(awk -F'\t' 'NR>1{s+=$4} END{printf "%.1f", s/1e6}' "$out")
    chains=$(awk -F'\t' 'NR>1 && $6!=""{print $6}' "$out" | sort -u | wc -l)
    printf '%-30s %10s %10s %10s %8s\n' "$name" "$ranges" "$stored" "$(( $(stat -c%s "$path") / 1000000 ))" "$chains"
done
