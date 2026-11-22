#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ${1:-} != --inside ]]; then
  cargo build --release --manifest-path explorer/Cargo.toml --offline
  exec xvfb-run -a -s '-screen 0 1280x900x24' "$0" --inside
fi
work=$(mktemp -d /tmp/annoyed-export-cancel.XXXXXX)
app=''
trap '[[ -z $app ]] || kill "$app" 2>/dev/null || true; rm -rf "$work"' EXIT
python3 tools/explorer_sparse_fixture.py "$work"
env -u WAYLAND_DISPLAY WINIT_UNIX_BACKEND=x11 explorer/target/release/annoyed-tools &
app=$!
for _ in {1..100}; do
  window=$(xdotool search --onlyvisible --name 'Annoyed Tools' 2>/dev/null | head -1 || true)
  [[ -n $window ]] && break
  sleep .1
done
test -n "${window:-}"
xdotool windowsize "$window" 1200 800
xdotool windowfocus "$window"
xdotool mousemove --window "$window" 150 74 click 1 type --clearmodifiers "$work/sparse.rpf"
xdotool key Return
sleep .5
xdotool mousemove --window "$window" 130 298 click 1 type --clearmodifiers "$work/sparse.tsv"
xdotool key Return
sleep .5
xdotool mousemove --window "$window" 120 514 click 1
sleep .3
xdotool mousemove --window "$window" 180 232 click 1 type --clearmodifiers "$work/payload.bin"
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/annoyed-export-cancel-before.png
xdotool mousemove --window "$window" 850 232 click 1
sleep .1
xdotool mousemove --window "$window" 1020 232 click 1
sleep 1
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/annoyed-export-cancel-after.png
tesseract /tmp/annoyed-export-cancel-after.png /tmp/annoyed-export-cancel-after 2>/dev/null
rg -qi 'Export cancelled' /tmp/annoyed-export-cancel-after.txt
test ! -e "$work/payload.bin"
if compgen -G "$work/payload.bin.partial-*" >/dev/null; then exit 1; fi
