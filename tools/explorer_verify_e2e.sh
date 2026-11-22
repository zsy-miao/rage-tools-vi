#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cargo build --release --manifest-path explorer/Cargo.toml --offline --no-default-features --bins
work=$(mktemp -d /tmp/annoyed-verify-e2e.XXXXXX)
explorer/target/release/annoyed-index data.rpf "$work/index.tsv"
explorer/target/release/annoyed-verify data.rpf "$work/index.tsv" > "$work/report.tsv"
rg -q '^zlib_streams\s+28509$' "$work/report.tsv"
archive_hash=$(sha256sum data.rpf | cut -d ' ' -f1)
index_hash=$(sha256sum "$work/index.tsv" | cut -d ' ' -f1)
rg -q "^archive_sha256\s+$archive_hash$" "$work/report.tsv"
rg -q "^index_sha256\s+$index_hash$" "$work/report.tsv"
