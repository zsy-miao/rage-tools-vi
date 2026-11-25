#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ${1:-} != --inside ]]; then
  cargo build --manifest-path explorer/Cargo.toml --offline --bins
  exec xvfb-run -a -s '-screen 0 1280x900x24' "$0" --inside
fi
work=$(mktemp -d /tmp/annoyed-image-e2e.XXXXXX)
app=''
trap '[[ -z $app ]] || kill "$app" 2>/dev/null || true; rm -rf "$work"' EXIT
python3 tools/explorer_image_fixture.py "$work" --format "${ANNOYED_IMAGE_FORMAT:-png}"
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
xdotool mousemove --window "$window" 150 74 click 1 type --clearmodifiers "$work/image.rpf"
xdotool key Return
sleep .5
xdotool mousemove --window "$window" 130 298 click 1 type --clearmodifiers "$work/image.tsv"
xdotool key Return
sleep .5
xdotool mousemove --window "$window" 120 514 click 1
sleep .8
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/annoyed-image-preview.png
python3 tools/explorer_image_fixture.py "$work" --assert-screenshot /tmp/annoyed-image-preview.png
