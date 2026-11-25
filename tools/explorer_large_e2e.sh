#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ${1:-} != --inside ]]; then
  cargo build --release --manifest-path explorer/Cargo.toml --offline
  exec xvfb-run -a -s '-screen 0 1280x900x24' "$0" --inside
fi
env -u WAYLAND_DISPLAY WINIT_UNIX_BACKEND=x11 explorer/target/release/annoyed-tools &
app=$!
trap 'kill "$app" 2>/dev/null || true' EXIT
for _ in {1..100}; do
  window=$(xdotool search --onlyvisible --name 'Annoyed Tools' 2>/dev/null | head -1 || true)
  [[ -n $window ]] && break
  sleep .1
done
test -n "${window:-}"
xdotool windowsize "$window" 1200 800
xdotool windowfocus "$window"
xdotool mousemove --window "$window" 150 74 click 1 type --clearmodifiers "$PWD/data.rpf"
xdotool key Return
sleep 1
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/annoyed-large-open.png
tesseract /tmp/annoyed-large-open.png /tmp/annoyed-large-open 2>/dev/null
rg -q '481544304 bytes' /tmp/annoyed-large-open.txt
index_path=$(mktemp -d /tmp/annoyed-large-e2e.XXXXXX)/index.tsv
xdotool mousemove --window "$window" 130 298 click 1 type --clearmodifiers "$index_path"
xdotool mousemove --window "$window" 80 340 click 1
sleep .3
xdotool mousemove --window "$window" 190 340 click 1
sleep 1
test ! -e "$index_path"
test -e "$index_path.partial"
test -e "$index_path.checkpoint"
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/annoyed-large-cancel.png
tesseract /tmp/annoyed-large-cancel.png /tmp/annoyed-large-cancel 2>/dev/null
rg -qi 'Paused' /tmp/annoyed-large-cancel.txt
xdotool mousemove --window "$window" 80 340 click 1
for _ in {1..200}; do
  [[ -f $index_path ]] && break
  sleep .1
done
test "$(rg -c '^zlib' "$index_path")" = 28509
test ! -e "$index_path.partial"
test ! -e "$index_path.checkpoint"
python3 tools/stream_index.py data.rpf --out "$(dirname "$index_path")/baseline.tsv"
diff -u <(rg '^zlib' "$index_path" | cut -f1-5) <(rg '^zlib' "$(dirname "$index_path")/baseline.tsv" | cut -f1-5)
