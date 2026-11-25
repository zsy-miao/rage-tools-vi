#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cargo build --manifest-path explorer/Cargo.toml --offline --no-default-features --bins
work=$(mktemp -d /tmp/annoyed-cli-e2e.XXXXXX)
explorer/target/debug/annoyed-index story000_bvh4.rpf "$work/index.tsv"
test "$(rg -c '^zlib' "$work/index.tsv")" = 4
explorer/target/debug/annoyed-extract zlib story000_bvh4.rpf 0x340 0x4f1 "$work/payload.xml"
printf '%s  %s\n' e20f1cc642fbd0cc83ef6dd1f5251d947c9793956e663ffa3cf48c1a332be57f "$work/payload.xml" | sha256sum -c -
if explorer/target/debug/annoyed-extract zlib story000_bvh4.rpf 0x340 0x4f0 "$work/incomplete"; then
  exit 1
fi
test ! -e "$work/incomplete"
explorer/target/debug/annoyed-headers core_licenses_data.rpf > "$work/headers.tsv"
rg -q '^0x1000' "$work/headers.tsv"
explorer/target/debug/annoyed-search story000_bvh4.rpf "$work/index.tsv" story000_terrain_bvh > "$work/search.tsv"
rg -q '^0x1000\s+0x1291' "$work/search.tsv"
explorer/target/debug/annoyed-verify story000_bvh4.rpf "$work/index.tsv" > "$work/verification.tsv"
rg -q '^zlib_streams\s+4$' "$work/verification.tsv"
rg -q '^archive_sha256\s+b9f86219f835c769ca86274f933ab35423af45dad33f130d5c5e4727450ffd24$' "$work/verification.tsv"
explorer/target/debug/annoyed-verify --expect "$work/verification.tsv" story000_bvh4.rpf "$work/index.tsv" > /dev/null
sed -i 's/story000_environment_bvh/story000_environment_bvH/g' "$work/index.tsv"
if explorer/target/debug/annoyed-verify --expect "$work/verification.tsv" story000_bvh4.rpf "$work/index.tsv" > /dev/null; then exit 1; fi
python3 tools/explorer_deflate_e2e.py --index-out "$work/deflate-index.tsv"
explorer/target/debug/annoyed-verify data.rpf "$work/deflate-index.tsv" > "$work/deflate-verification.tsv"
rg -q '^raw_deflate_streams\s+1$' "$work/deflate-verification.tsv"
explorer/target/debug/annoyed-search data.rpf "$work/deflate-index.tsv" uiCreditsPageData > "$work/deflate-search.tsv"
rg -q '^0x966000\s+0x966308\s+1318\s+raw_deflate$' "$work/deflate-search.tsv"
