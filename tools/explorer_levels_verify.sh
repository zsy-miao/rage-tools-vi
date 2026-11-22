#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source_archive='/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK/levels.rpf'
cargo build --release --manifest-path explorer/Cargo.toml --offline --no-default-features --bin annoyed-verify
mkdir -p cache
work=$(mktemp -d "$PWD/cache/annoyed-levels-verify.XXXXXX")
printf 'Results: %s\n' "$work"
/usr/bin/time -v -o "$work/time.txt" explorer/target/release/annoyed-verify --progress "$source_archive" output/index/levels.tsv > "$work/report.tsv"
cat "$work/report.tsv"
