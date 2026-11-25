#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source_archive='/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK/anim.rpf'
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
xdotool mousemove --window "$window" 150 74 click 1 type --clearmodifiers "$source_archive"
xdotool key Return
sleep 1
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/annoyed-anim-open.png
tesseract /tmp/annoyed-anim-open.png /tmp/annoyed-anim-open 2>/dev/null
rg -q '4407626384 bytes' /tmp/annoyed-anim-open.txt
xdotool mousemove --window "$window" 130 298 click 1 type --clearmodifiers "$PWD/output/index/anim.tsv"
xdotool key Return
sleep 1
xdotool mousemove --window "$window" 120 546 click 1
sleep 1
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/annoyed-anim-preview.png
ffmpeg -loglevel error -y -i /tmp/annoyed-anim-preview.png -vf 'crop=680:400:490:200,scale=1360:800' /tmp/annoyed-anim-preview-crop.png
tesseract /tmp/annoyed-anim-preview-crop.png /tmp/annoyed-anim-preview 2>/dev/null
rg -qi 'binary' /tmp/annoyed-anim-preview.txt
xdotool mousemove --window "$window" 230 160 click 1 key ctrl+a
xdotool type --clearmodifiers 0x100000000
xdotool key Return
sleep 1
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/annoyed-anim-offset.png
ffmpeg -loglevel error -y -i /tmp/annoyed-anim-offset.png -vf 'crop=680:400:490:200,scale=1360:800' /tmp/annoyed-anim-offset-crop.png
tesseract /tmp/annoyed-anim-offset-crop.png /tmp/annoyed-anim-offset 2>/dev/null
rg -q '0000000?100000010' /tmp/annoyed-anim-offset.txt
xdotool mousemove --window "$window" 130 375 click 1 type --clearmodifiers __annoyed_search_cancellation_control__
xdotool mousemove --window "$window" 330 340 click 1
sleep .2
xdotool mousemove --window "$window" 416 340 click 1
sleep .5
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/annoyed-anim-search-cancel.png
tesseract /tmp/annoyed-anim-search-cancel.png /tmp/annoyed-anim-search-cancel 2>/dev/null
rg -qi 'Search cancelled' /tmp/annoyed-anim-search-cancel.txt
xdotool mousemove --window "$window" 720 82 click 1
sleep .2
xdotool mousemove --window "$window" 835 82 click 1
sleep .5
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/annoyed-anim-verify-cancel.png
tesseract /tmp/annoyed-anim-verify-cancel.png /tmp/annoyed-anim-verify-cancel 2>/dev/null
rg -qi 'Verification cancelled' /tmp/annoyed-anim-verify-cancel.txt
