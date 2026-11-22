#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cargo build --release --manifest-path explorer/Cargo.toml --no-default-features --offline --bin annoyed-index
work=$(mktemp -d /tmp/annoyed-resume-e2e.XXXXXX)
source_archive=data.rpf
delay=.3
if [[ ${ANNOYED_RESUME_LARGE:-0} == 1 ]]; then
  source_archive='/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK/anim.rpf'
  delay=6
fi
explorer/target/release/annoyed-index --resume "$source_archive" "$work/resumed.tsv" &
worker=$!
for _ in {1..100}; do
  [[ -e "$work/resumed.tsv.checkpoint" ]] && break
  sleep .05
done
test -e "$work/resumed.tsv.checkpoint"
sleep "$delay"
kill -KILL "$worker"
wait "$worker" 2>/dev/null || true
test ! -e "$work/resumed.tsv"
if [[ ${ANNOYED_RESUME_LARGE:-0} == 1 ]]; then
  checkpoint_position=$(od -An -tu8 -j40 -N8 "$work/resumed.tsv.checkpoint" | tr -d ' ')
  test "$checkpoint_position" -gt 18016
fi
explorer/target/release/annoyed-index --resume "$source_archive" "$work/resumed.tsv"
baseline="$work/baseline.tsv"
if [[ ${ANNOYED_RESUME_LARGE:-0} == 1 ]]; then
  baseline=output/index/anim.tsv
else
  python3 tools/stream_index.py data.rpf --out "$baseline"
fi
diff -u <(rg '^zlib' "$work/resumed.tsv" | cut -f1-5) <(rg '^zlib' "$baseline" | cut -f1-5)
test ! -e "$work/resumed.tsv.partial"
test ! -e "$work/resumed.tsv.checkpoint"
