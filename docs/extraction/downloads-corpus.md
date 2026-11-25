# Downloads corpus

The source tree `GTA6.Xbox.v1.0.2.1-CYBERLEEK` contains **22 RPF9 files /
161,307,137,472 bytes**. The canonical copy is the external volume; keep it
read-only and do not duplicate it.

## Inventory

| Metric | Value |
| --- | ---: |
| RPF9 files | 22 |
| total bytes | 161,307,137,472 |
| indexed archives | 8 large archives |
| indexed zlib streams | 2,190,635 |
| indexed decoded bytes | 360,572,388,767 |
| fully extracted archives | 6 |
| index-only archives | `levels`, `movies` |

The smaller repository samples are verified byte-for-byte and are used by the
Rust path. The eight large archives are handled by `stream_index.py` and
`bulk_extract.py`.

## Current rebuild

On 2026-11-21 the output set was deleted and rebuilt from source:

```text
output/index/                8 streaming indexes
output/extracted/            anim, packs, navmeshes, core_bvh4, story000, audio
output/extracted/audio-awc/  6,625 ADAT containers
output/extracted/audio-xma2/ 151 decoded WAVs
output/verification.tsv      6/6 PASS rows
```

`levels` and `movies` are indexed only. `levels` decodes to about **174.9 GB**;
extract it after moving the output set to the external volume.

## Selective access

`tools/stream_index.py` creates a bounded-memory index of every zlib span in an
archive. `tools/bulk_extract.py` consumes that index; `tools/verify_bulk.py`
checks file sizes and SHA-256 against the index.

```sh
python3 tools/stream_index.py "$archive" --out "$index"
python3 tools/bulk_extract.py "$archive" "$index" "$out_dir" --resume
python3 tools/verify_bulk.py "$archive" "$index" "$out_dir/manifest.tsv"
```

The full reproducible run is:

```sh
tools/export_all.sh SOURCE_ROOT OUTPUT_ROOT
```

## Artifacts

- `handoff/downloads-corpus-inventory.tsv` — relative path, stored bytes, magic,
  extraction manifest.
- `handoff/remaining-archive-index-summary.tsv` — index counts and timings.
- `handoff/bulk-extraction-verification-summary.tsv` — verified extract rows.
