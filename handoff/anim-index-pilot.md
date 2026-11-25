# anim.rpf index pilot

Read-only pilot on the smallest outstanding Downloads archive.

## Tested

```bash
target/debug/rage-tools-vi map ~/Downloads/GTA6.Xbox.v1.0.2.1-CYBERLEEK/anim.rpf \
  > /tmp/anim-map.tsv
```

| Metric | Value |
| --- | ---: |
| wall time | 3m49s |
| peak RSS | 4,340,508 KiB (4.34 GB) |
| index rows | 259,138 |
| index bytes | 11 MB |
| stored bytes | 4,407,626,384 |
| decoded bytes | 11,572,883,428 |
| zlib ranges | 130,509 |
| zero_run ranges | 128,127 |
| unclassified ranges | 500 / 37,742,843 bytes |
| coverage | 100% |

Selective extraction of `0x6000..0x62dc`:

```bash
python3 tools/mmap_extract.py ~/Downloads/GTA6.Xbox.v1.0.2.1-CYBERLEEK/anim.rpf \
  --start 0x6000 --end 0x62dc --output /tmp/anim-one.bin
```

- `mmap` path: 2,808 bytes, 15,428 KiB RSS, 0.0s,
  sha256 `cbdb4e9d1ecbe7ff0a197f759c47c0c5f0f88ebb0830ee6af958ef6949b430e4`;
- Rust `extract-zlib`: same hash, 4.31 GB RSS, 3.69s.

## Streaming follow-up

`tools/stream_index.py` scans with a read-only mmap, zlib chunks, and periodic
`madvise`:

```bash
/usr/bin/time -v python3 tools/stream_index.py \
  ~/Downloads/GTA6.Xbox.v1.0.2.1-CYBERLEEK/anim.rpf --out /tmp/stream-anim.tsv
```

| Metric | Rust `map` | stream_index |
| --- | ---: | ---: |
| wall | 3m49s | 29.08s |
| peak RSS | 4.34 GB | 333 MB |
| spans | 259,138 | 258,152 |
| zlib streams | 130,509 | 130,510 |
| decoded bytes | 11,572,883,428 | 11,593,461,732 |

The streaming scanner found one additional valid stream at
`0xed61e010..0xee4ff55f`, decoding 20,578,304 bytes. Rust missed it because
`MAX_PAYLOAD_SIZE` is 16 MiB. This is a real coverage bug in the current Rust
path, not just a memory issue.

## Blocker

`src/main.rs` still calls `fs::read()` for the whole archive. `map` and
`extract-zlib` therefore need archive-size RAM. `stream_index.py` now provides a
bounded index path (333 MB on a 4.4 GB archive), and `mmap_extract.py` provides
bounded selective extraction.

The Rust `MAX_PAYLOAD_SIZE = 16 MiB` also rejects valid larger streams. It must
be raised or made streaming before trusting Rust `map`/`extract` coverage on
the remaining large archives.

## Proposed order

1. `anim.rpf` — pilot complete.
2. `packs.rpf` (~4.8 GB).
3. `navmeshes.rpf` (~6.7 GB).
4. `pack/core_bvh4/core_bvh4.rpf` (~8.3 GB).
5. `movies.rpf` (~8.8 GB).
6. `pack/story000/story000.rpf` (~20.0 GB).
7. `audio.rpf` (~28.5 GB).
8. `levels.rpf` (~76.2 GB).

## Streaming index cross-check

The streaming run in commit `643ced8` took 38.25 seconds and used 53,772 KiB
peak RSS. All 130,509 ordered zlib start offsets, exclusive ends and decoded
lengths match the independent Rust map. The front and trailer match exactly.
Coalescing the Rust zero runs and unclassified spans reproduces the streaming
gap boundaries. Nine distributed streams were independently inflated and
hashed. Both extraction paths returned the same 2,808 bytes at offset 0x6000.
The streaming index is available in the Downloads catalog under anim.rpf.
