#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ${1:-} != --inside ]]; then
  cargo build --manifest-path explorer/Cargo.toml --offline
  exec xvfb-run -a -s '-screen 0 1280x900x24' "$0" --inside
fi
env -u WAYLAND_DISPLAY WINIT_UNIX_BACKEND=x11 explorer/target/debug/annoyed-tools &
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
xdotool mousemove --window "$window" 150 74 click 1 type --clearmodifiers "$PWD/story000_bvh4.rpf"
xdotool key Return
sleep 1
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/rage-explorer-e2e.png
tesseract /tmp/rage-explorer-e2e.png /tmp/rage-explorer-e2e 2>/dev/null
rg -q '5632 bytes' /tmp/rage-explorer-e2e.txt
index_path=$(mktemp -d /tmp/annoyed-index-e2e.XXXXXX)/index.tsv
xdotool mousemove --window "$window" 130 298 click 1 type --clearmodifiers "$index_path"
xdotool mousemove --window "$window" 80 340 click 1
for _ in {1..100}; do
  [[ -f $index_path ]] && [[ $(rg -c '^zlib' "$index_path" || true) == 4 ]] && break
  sleep .1
done
test "$(rg -c '^zlib' "$index_path")" = 4
sleep .5
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/rage-explorer-index.png
ffmpeg -loglevel error -y -i /tmp/rage-explorer-index.png -vf 'crop=460:500:0:200,scale=920:1000' /tmp/rage-explorer-index-crop.png
tesseract /tmp/rage-explorer-index-crop.png /tmp/rage-explorer-index 2>/dev/null
xdotool mousemove --window "$window" 720 82 click 1
sleep 1
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/rage-explorer-verify.png
ffmpeg -loglevel error -y -i /tmp/rage-explorer-verify.png -vf 'crop=680:400:490:200,scale=1360:800' /tmp/rage-explorer-verify-crop.png
tesseract /tmp/rage-explorer-verify-crop.png /tmp/rage-explorer-verify 2>/dev/null
rg -qi 'Coverage and zlib checks passed' /tmp/rage-explorer-verify.txt
xdotool mousemove --window "$window" 955 82 click 1
for _ in {1..50}; do
  [[ -f "$index_path.baseline.tsv" ]] && break
  sleep .1
done
test -f "$index_path.baseline.tsv"
xdotool mousemove --window "$window" 1100 82 click 1
sleep .5
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/rage-explorer-baseline.png
tesseract /tmp/rage-explorer-baseline.png /tmp/rage-explorer-baseline 2>/dev/null
rg -qi 'Baseline matches' /tmp/rage-explorer-baseline.txt
xdotool mousemove --window "$window" 185 449 click 1
sleep .5
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/rage-explorer-quadrant.png
ffmpeg -loglevel error -y -i /tmp/rage-explorer-quadrant.png -vf 'crop=470:350:0:250,scale=940:700' /tmp/rage-explorer-quadrant-crop.png
tesseract /tmp/rage-explorer-quadrant-crop.png /tmp/rage-explorer-quadrant 2>/dev/null
rg -qi 'Byte slice.*1080' /tmp/rage-explorer-quadrant.txt
xdotool mousemove --window "$window" 235 449 click 1
sleep .5
xdotool mousemove --window "$window" 120 504 click 1
sleep 1
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/rage-explorer-preview.png
ffmpeg -loglevel error -y -i /tmp/rage-explorer-preview.png -vf 'crop=680:400:490:200,scale=1360:800' /tmp/rage-explorer-preview-crop.png
tesseract /tmp/rage-explorer-preview-crop.png /tmp/rage-explorer-preview 2>/dev/null
rg -qi 'Decoded text preview' /tmp/rage-explorer-preview.txt
destination=$(mktemp -d /tmp/annoyed-tools-e2e.XXXXXX)/payload.xml
xdotool mousemove --window "$window" 180 232 click 1 type --clearmodifiers "$destination"
xdotool mousemove --window "$window" 845 232 click 1
for _ in {1..50}; do
  [[ -f $destination ]] && [[ $(wc -c < "$destination") == 800 ]] && break
  sleep .1
done
printf '%s  %s\n' e20f1cc642fbd0cc83ef6dd1f5251d947c9793956e663ffa3cf48c1a332be57f "$destination" | sha256sum -c -
xdotool mousemove --window "$window" 130 375 click 1 type --clearmodifiers story000_terrain_bvh
xdotool key Return
sleep 1
xdotool mousemove --window "$window" 120 484 click 1
sleep 1
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/rage-explorer-search.png
ffmpeg -loglevel error -y -i /tmp/rage-explorer-search.png -vf 'crop=680:400:490:200,scale=1360:800' /tmp/rage-explorer-search-crop.png
tesseract /tmp/rage-explorer-search-crop.png /tmp/rage-explorer-search 2>/dev/null
rg -qi 'story000_terrain_bvh' /tmp/rage-explorer-search.txt
raw_path=$(dirname "$destination")/raw.bin
xdotool mousemove --window "$window" 180 232 click 1 key ctrl+a
xdotool type --clearmodifiers "$raw_path"
xdotool mousemove --window "$window" 720 232 click 1
for _ in {1..50}; do
  [[ -f $raw_path ]] && [[ $(wc -c < "$raw_path") == 657 ]] && break
  sleep .1
done
dd if=story000_bvh4.rpf of="$(dirname "$destination")/expected.bin" bs=1 skip=4096 count=657 status=none
cmp "$raw_path" "$(dirname "$destination")/expected.bin"
xdotool mousemove --window "$window" 230 160 click 1 key ctrl+a
xdotool type --clearmodifiers 0x12a0
xdotool key Return
sleep .3
xdotool mousemove --window "$window" 220 413 click 1
sleep .5
xdotool mousemove --window "$window" 100 484 click 1
sleep .5
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/rage-explorer-seek.png
ffmpeg -loglevel error -y -i /tmp/rage-explorer-seek.png -vf 'crop=680:400:490:200,scale=1360:800' /tmp/rage-explorer-seek-crop.png
tesseract /tmp/rage-explorer-seek-crop.png /tmp/rage-explorer-seek 2>/dev/null
rg -qi 'ContentDef' /tmp/rage-explorer-seek.txt
if rg -q 's16_w17_bvh' "$index_path"; then exit 1; fi
xdotool mousemove --window "$window" 130 375 click 1 key ctrl+a
xdotool type --clearmodifiers s16_w17_bvh
xdotool mousemove --window "$window" 330 340 click 1
sleep 1
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/rage-explorer-full-search.png
ffmpeg -loglevel error -y -i /tmp/rage-explorer-full-search.png -vf 'crop=470:350:0:250,scale=940:700' /tmp/rage-explorer-full-search-crop.png
tesseract /tmp/rage-explorer-full-search-crop.png /tmp/rage-explorer-full-search 2>/dev/null
rg -qi 'Full decoded search' /tmp/rage-explorer-full-search.txt
xdotool mousemove --window "$window" 120 504 click 1
sleep .5
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/rage-explorer-full-result.png
ffmpeg -loglevel error -y -i /tmp/rage-explorer-full-result.png -vf 'crop=680:400:490:200,scale=1360:800' /tmp/rage-explorer-full-result-crop.png
tesseract /tmp/rage-explorer-full-result-crop.png /tmp/rage-explorer-full-result 2>/dev/null
rg -qi 'story000_terrain_bvh' /tmp/rage-explorer-full-result.txt
xdotool mousemove --window "$window" 180 82 click 1 key ctrl+a
xdotool type --clearmodifiers "$PWD/core_licenses_data.rpf"
xdotool key Return
sleep .5
xdotool mousemove --window "$window" 315 414 click 1
sleep .5
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/rage-explorer-headers.png
ffmpeg -loglevel error -y -i /tmp/rage-explorer-headers.png -vf 'crop=470:350:0:250,scale=940:700' /tmp/rage-explorer-headers-crop.png
tesseract /tmp/rage-explorer-headers-crop.png /tmp/rage-explorer-headers 2>/dev/null
rg -qi 'header candidates' /tmp/rage-explorer-headers.txt
xdotool mousemove --window "$window" 120 536 click 1
sleep .5
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/rage-explorer-header-select.png
ffmpeg -loglevel error -y -i /tmp/rage-explorer-header-select.png -vf 'crop=680:250:490:250,scale=1360:500' /tmp/rage-explorer-header-select-crop.png
tesseract /tmp/rage-explorer-header-select-crop.png /tmp/rage-explorer-header-select 2>/dev/null
rg -q '0{9,12}1030' /tmp/rage-explorer-header-select.txt
xdotool mousemove --window "$window" 180 82 click 1 key ctrl+a
xdotool type --clearmodifiers "$PWD/story000_bvh4.rpf"
xdotool key Return
sleep .5
sed -i 's/story000_environment_bvh/story000_environment_bvH/g' "$index_path"
xdotool mousemove --window "$window" 1100 82 click 1
sleep 3
ffmpeg -loglevel error -y -f x11grab -video_size 1280x900 -i "$DISPLAY" -frames:v 1 /tmp/rage-explorer-baseline-mismatch.png
tesseract /tmp/rage-explorer-baseline-mismatch.png /tmp/rage-explorer-baseline-mismatch 2>/dev/null
rg -qi 'differs from baseline' /tmp/rage-explorer-baseline-mismatch.txt
