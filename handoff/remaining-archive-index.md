# Remaining eight archive indexes

Streaming `mmap` indexes are complete for all eight outstanding Downloads
archives. Every index asserts full stored-byte coverage. Indexes are local under
`output/downloads-corpus/index/` (184 MB total), not a second corpus copy.

| Archive | Stored bytes | Spans | zlib | Decoded bytes | Unclassified | >16 MiB | Wall | Peak RSS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| anim.rpf | 4,407,626,384 | 258,152 | 130,510 | 11,593,461,732 | 256 | 1 | 29.08s | 333 MB |
| packs.rpf | 4,798,213,264 | 285,069 | 144,366 | 9,735,393,283 | 1,261 | 4 | 35.83s | 926 MB |
| navmeshes.rpf | 6,707,512,496 | 178,941 | 90,305 | 20,551,068,944 | 30 | 0 | 59.44s | 782 MB |
| pack/core_bvh4/core_bvh4.rpf | 8,297,921,520 | 1,113,186 | 565,596 | 129,929,580,001 | 1,262 | 38 | 316.80s | 363 MB |
| movies.rpf | 8,832,481,776 | 3 | 0 | 0 | 1 | 0 | 18.04s | 8.11 GB |
| pack/story000/story000.rpf | 20,022,508,672 | 279,306 | 141,163 | 13,766,986,233 | 838 | 13 | 87.05s | 8.16 GB |
| audio.rpf | 28,543,454,672 | 1,629 | 838 | 54,143,545 | 3 | 0 | 73.14s | 15.91 GB |
| levels.rpf | 76,155,065,056 | 2,199,213 | 1,117,857 | 174,941,755,029 | 22,421 | 40 | 819.07s | 1.21 GB |
| **total** | **157,764,783,840** | **4,315,499** | **2,190,635** | **360,572,388,767** | **26,072** | **96** | | |

## Rust cap failure

`MAX_PAYLOAD_SIZE = 16 MiB` loses **96 valid streams**. Concrete test:

```bash
python3 tools/mmap_extract.py anim.rpf --start 0xed61e010 --end 0xee4ff55f --output /tmp/anim-large.bin
# 20,578,304 bytes, 91 MB RSS, sha256 e9600e6f…c7c9
target/debug/rage-tools-vi extract-zlib anim.rpf 0xed61e010 0xee4ff55f /tmp/rust.bin
# no checksum-valid zlib stream at 0xed61e010
```

The Rust cap must be raised or made streaming before using Rust `map`/`extract`
for coverage on these archives.
