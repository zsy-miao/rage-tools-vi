# story000_bvh4 control evidence pack

2026-11-21. Four exact XML payloads and source extents from
`/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK/pack/story000_bvh4/story000_bvh4.rpf`.

## Archive coverage

- Source size: **5,632 bytes**
- Spans: **10** (front 1, zlib 4, zero run 4, trailer 1)
- Stored in zlib: **1,795 bytes**
- Decoded XML: **16,677 bytes**
- Verification: **4/4 manifest rows, missing 0, extra 0, failures 0, PASS**

## XML ranges

| start | end | stored | decoded | XML root | XML id | SHA-256 |
| --- | --- | ---: | ---: | --- | --- | --- |
| `0x340` | `0x4f1` | 433 | 800 | `CDataFileMgr__ContentChangeSetDef` | `story000_environment_bvh` | `e20f1cc642fbd0cc83ef6dd1f5251d947c9793956e663ffa3cf48c1a332be57f` |
| `0x1000` | `0x1291` | 657 | 14,426 | `CDataFileMgr__ContentChangeSetDef` | `story000_terrain_bvh` | `e3ce4547f1336d7b6435f5f62a5724cbf12d1f2c10a27cc7e7dc8b71177b3675` |
| `0x12a0` | `0x13bd` | 285 | 622 | `CDataFileMgr__ContentDef` | — | `4788072c0f7d5001b7fb796906b744808e9d1cfd3e9263630fe957eab50ab4c6` |
| `0x13c0` | `0x1564` | 420 | 829 | `SSetupData` | — | `24d6b96ab07341b2ed93bac2e99239d1afd9897d043323176bd98f3282fb4245` |

Machine-readable table: `handoff/story000-bvh4-control.tsv`.

## Reproduce

```sh
SRC=/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK/pack/story000_bvh4/story000_bvh4.rpf
OUT=output/story000-bvh4-control
python3 tools/stream_index.py "$SRC" --out "$OUT/index.tsv"
python3 tools/bulk_extract.py "$SRC" "$OUT/index.tsv" "$OUT/payload" --manifest "$OUT/manifest.tsv"
python3 tools/verify_bulk.py "$SRC" "$OUT/index.tsv" "$OUT/manifest.tsv" --out "$OUT/verification.tsv"
python3 tools/story000_bvh4_control.py --index "$OUT/index.tsv" --manifest "$OUT/manifest.tsv"
```

The archive is small enough to reproduce exactly; the four payloads are local
under `output/story000-bvh4-control/payload/`. The control is for the Front A
entry→payload test; it does not decode the Front A table itself.
