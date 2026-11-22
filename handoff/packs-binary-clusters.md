# packs binary ML clusters

Pilot: 113,480 `binary` streams, 32 MiniBatchKMeans clusters. Features are
byte-level: size, leading-zero offset, entropy, zero/printable fractions, u16/u32
statistics, 16-bin byte histogram, first 16 bytes after zeros, and 16 hashed
bigrams. ML is a **proposal engine**, not a verifier.

## Cluster families

| Cluster | Streams | Avg bytes | Top head | Reading |
| ---: | ---: | ---: | --- | --- |
| 4 | 15,888 | 23,804 | `2035005000000000` | zero-prefixed table; `...0050` words |
| 1 | 12,791 | 1,080 | `a001005000000000` | small table; `...0050` |
| 9 | 7,254 | 236 | `d000005000000000` | small table |
| 12 | 6,403 | 1,538 | `2002005000000000` | table |
| 31 | 6,284 | 3,172 | `9003005000000000` | table |
| 29 | 5,926 | 6,039 | `b00b005000000000` | table |
| 18 | 5,296 | 23,849 | `5073005000000000` | table |
| 17 | 4,687 | 13,330 | `8c090000b0090000` | paired counts |
| 6 | 3,966 | 54,187 | `b060000064610000` | paired words |
| 15 | 3,712 | 4,797 | `0200500000000000` | table |
| 14 | 3,711 | 141,095 | `602f005000000000` | large table |
| 22 | 2,964 | 55,212 | `4040000098430000` | distinct `0x4040` family |
| 7 | 2,021 | 22,949 | `0e0000802a060000` | sibling of `0f000080` |
| 25 | 983 | 54,286 | `474d5f5530315f43` | ASCII `GM_U01_C` family |
| 23 | 338 | 26,347 | `ffffff7fffff0000` | float/Nan-like |

The `...0050` high word appears across many zero-prefixed clusters, suggesting a
pointer/table family. `0e000080` is a sibling of the known `0f000080` header.
`GM_U01_C` is a visible ASCII header family; `0x4040` is distinct from the known
`0x4042` family.

## Caveats

- Clusters are unsupervised; labels are not ground truth.
- Leading zeros are stripped before features, but the details retain the raw
  head.
- Cluster membership is dominated by size and header statistics; do not infer
  semantics from a cluster name.
- Re-run with different `--clusters` / features and compare before trusting a
  label.

Artifacts: `handoff/packs-binary-clusters.tsv`; detailed local membership
`output/packs-binary-clusters.tsv`; tool `tools/ml_binary_clusters.py`.

## Active-learning queue

`handoff/packs-label-queue.tsv` contains 128 representatives (four variants per
cluster) with `cluster`, `rank`, `start`, size, first non-zero head, zero
offset, path, empty `label`, and note. Labels from the operator feed the next
supervised classifier; the deterministic verifier remains ground truth.
