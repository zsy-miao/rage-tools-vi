# Corpus pass

Every `*.rpf` in the source directory, indexed and measured with the current tools. `Exact model` is the share of packs whose declared entry count is reproduced exactly by one of the simple entry models (`single`, `pairs`, `chains`, `structs-1`, `pos-pairs`); `Entries` is the payload-derived manifest size where one was emitted.

| Archive | Ranges | zlib | Stored GB | Packs | Exact model | Unit | Entries |
| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| `anim.rpf` | 258,152 | 130,510 | 4.4 | 235 | 53% | chains | 5826 |
| `appdata0.rpf` | 3 | 0 | 0.0 | 0 | — | — | — |
| `audio.rpf` | 1,629 | 838 | 28.5 | 1 | 0% | — | — |
| `common.rpf` | 1,871 | 954 | 0.0 | 1 | 0% | pairs | 0 |
| `core_bvh4.rpf` | 1,113,186 | 565,596 | 8.3 | 1261 | 99% | pairs | 109301 |
| `core_licenses_data.rpf` | 9 | 3 | 0.0 | 1 | 100% | — | — |
| `core_restofworld.rpf` | 4,659 | 2,371 | 1.3 | 10 | 50% | pairs | 801 |
| `core_restofworld001.rpf` | 69 | 33 | 0.0 | 1 | 0% | chains | 0 |
| `data.rpf` | 56,583 | 28,509 | 0.5 | 40 | 40% | chains | 2063 |
| `levels.rpf` | 2,199,213 | 1,117,857 | 76.2 | 2044 | 36% | pairs | 29117 |
| `movies.rpf` | 3 | 0 | 8.8 | 0 | — | — | — |
| `navmeshes.rpf` | 178,941 | 90,305 | 6.7 | 28 | 50% | chains | 23530 |
| `packs.rpf` | 285,069 | 144,366 | 4.8 | 59 | 34% | pairs | 15983 |
| `script.rpf` | 1,997 | 1,057 | 0.0 | 2 | 50% | single | — |
| `shaders.rpf` | 8,180 | 4,205 | 0.4 | 1 | 0% | chains | 0 |
| `shared_minigame000.rpf` | 10,004 | 5,074 | 0.8 | 44 | 73% | chains | 210 |
| `shared_minigame000_bvh4.rpf` | 4,985 | 2,560 | 0.1 | 8 | 100% | pairs | 128 |
| `story000.rpf` | 279,306 | 141,163 | 20.0 | 419 | 30% | — | — |
| `story000_bvh4.rpf` | 10 | 4 | 0.0 | 1 | 100% | single | — |
| `story000_restofworld.rpf` | 1,237 | 624 | 0.2 | 16 | 56% | chains | 13 |
| `story000_script.rpf` | 5,248 | 2,632 | 0.1 | 1 | 0% | — | — |
| `textures.rpf` | 5,496 | 2,749 | 0.2 | 20 | 85% | pairs | 1326 |
| **total** | **4,415,868** | **2,241,410** | **161.3** | | | | |

Regenerate with `tools/corpus_pass.sh <source> --entries` and `python3 tools/corpus_report.py --write docs/extraction/corpus.md`.
