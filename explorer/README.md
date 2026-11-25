# Annoyed Tools

An early desktop explorer for RPF9 research. Open an archive, then create an
index or load a matching stream index TSV (as produced by `tools/stream_index.py`). Select a
range to view raw bytes or a bounded zlib text preview. A selected zlib stream
can be exported as raw bytes or decoded to a new file; existing files are never overwritten. Index
ranges are carved streams, not independently decoded archive entries. Match
the index to the source yourself; it checks the total size but does not verify provenance.
The indexer discovers zlib streams; raw-DEFLATE support applies only when an
independently established range is supplied as `raw_deflate` in an index or to
the extraction CLI.
The Headers view scans page-aligned RPF9 candidates in bounded batches; these
are not confirmed pack boundaries or decoded archive entries.
Q1–Q4 subdivide the archive byte extent; Up returns to the parent slice.
Ranges crossing a slice boundary can appear in multiple slices. These slices
do not imply pack membership.

```sh
cargo run --manifest-path explorer/Cargo.toml --release
cargo run --manifest-path explorer/Cargo.toml --no-default-features --release --bin annoyed-index -- --resume story000_bvh4.rpf /tmp/story-index.tsv
cargo run --manifest-path explorer/Cargo.toml --no-default-features --release --bin annoyed-extract -- zlib story000_bvh4.rpf 0x340 0x4f1 /tmp/story.xml
cargo run --manifest-path explorer/Cargo.toml --no-default-features --release --bin annoyed-headers -- core_licenses_data.rpf
cargo run --manifest-path explorer/Cargo.toml --no-default-features --release --bin annoyed-search -- story000_bvh4.rpf /tmp/story-index.tsv terrain
cargo run --manifest-path explorer/Cargo.toml --no-default-features --release --bin annoyed-verify -- story000_bvh4.rpf /tmp/story-index.tsv
tools/explorer_e2e.sh
tools/explorer_large_e2e.sh
tools/explorer_anim_e2e.sh
tools/explorer_cli_e2e.sh
tools/explorer_resume_e2e.sh
tools/explorer_export_cancel_e2e.sh
tools/explorer_verify_e2e.sh
tools/explorer_image_e2e.sh
ANNOYED_IMAGE_FORMAT=jpeg tools/explorer_image_e2e.sh
```

The archive and index are accessed in bounded pages, and the export decoder
streams to disk. GUI indexing can be paused and resumed at the same destination;
the CLI opts in with `--resume`. Checkpoints use adjacent `.partial`,
`.checkpoint`, and `.lock` files. Resumption verifies the partial index hash and
source size, modification time, path and sampled head/tail hash; these source
samples are not a whole-file identity check. Final publication requires hard-link
support in the destination filesystem. Index search checks at most 4096
rows per page; use Next to continue when a batch has no matches. New indexes
include up to 512 decoded bytes of text for prefix search; older indexes do not.
Full search streams indexed zlib and raw-DEFLATE content, is case-sensitive,
and processes at most 4,096 index rows per GUI batch; Next continues the search.
Verification checks range coverage, zlib checksums, raw-DEFLATE termination and
sizes, and zero runs, and computes archive/index SHA-256 baselines. Raw DEFLATE
has no checksum. Save baseline writes a new `<index>.baseline.tsv`; Compare
baseline repeats verification and checks both complete-file hashes. This does
not establish decoded entry records.
PNG/JPEG preview is limited to 8 MiB of encoded data and 2,048×2,048 pixels.
The interface does not yet offer archive tree navigation,
model or native RAGE texture previews, or archive editing. Tests so far cover one sparse
1 TiB file and the local `story000_bvh4.rpf` control; they do not establish
performance on petabyte-scale inputs.
