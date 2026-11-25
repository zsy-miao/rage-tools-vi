#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ${1:-} != --inside ]]; then
  cargo build --manifest-path explorer/Cargo.toml --offline --bins
  exec xvfb-run -a -s '-screen 0 1280x900x24' "$0" --inside
fi
work=$(mktemp -d /tmp/annoyed-deflate-ui.XXXXXX)
app=''
trap '[[ -z $app ]] || kill "$app" 2>/dev/null || true; rm -rf "$work"' EXIT
python3 tools/explorer_deflate_e2e.py --index-out "$work/index.tsv"
env -u WAYLAND_DISPLAY WINIT_UNIX_BACKEND=x11 explorer/target/debug/annoyed-tools &
app=$!
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
sleep .5
xdotool mousemove --window "$window" 130 298 click 1 type --clearmodifiers "$work/index.tsv"
xdotool key Return
sleep .5
xdotool mousemove --window "$window" 120 514 click 1
sleep .5
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/annoyed-deflate-ui.png
ffmpeg -loglevel error -y -i /tmp/annoyed-deflate-ui.png -vf 'crop=680:300:490:200,scale=1360:600' /tmp/annoyed-deflate-ui-crop.png
tesseract /tmp/annoyed-deflate-ui-crop.png /tmp/annoyed-deflate-ui 2>/dev/null
rg -qi 'raw DEFLATE has no checksum' /tmp/annoyed-deflate-ui.txt
xdotool mousemove --window "$window" 180 232 click 1 type --clearmodifiers "$work/output.bin"
xdotool mousemove --window "$window" 990 232 click 1
for _ in {1..50}; do
  [[ -f "$work/output.bin" ]] && break
  sleep .1
done
test "$(wc -c < "$work/output.bin")" = 1318
test "$(head -c 4 "$work/output.bin")" = RBF0
