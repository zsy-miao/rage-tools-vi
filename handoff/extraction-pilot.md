# Standalone RPF extraction browser

2026-11-21. Open the generated HTML directly from disk. The generator uses
the eight rebuilt indexes, six extracted manifests, and
`output/verification.tsv`. It reads one control file per verified archive to
check its size and SHA-256. It performs no reindex, extraction, or copying.

## Run

```sh
python3 tools/extraction_index_pilot.py
# Open output/extraction-index-pilot/index.html.
```

| Archive | Index ranges shown | Total index ranges | Verified ranges shown |
| --- | ---: | ---: | ---: |
| `audio.rpf` | 1,629 | 1,629 | 838 |
| `anim.rpf` | 96 | 258,152 | 46 |
| `core_bvh4.rpf` | 96 | 1,113,186 | 46 |
| `levels.rpf` | 96 | 2,199,213 | 0 |
| `movies.rpf` | 3 | 3 | 0 |
| `navmeshes.rpf` | 96 | 178,941 | 46 |
| `packs.rpf` | 96 | 285,069 | 47 |
| `story000.rpf` | 96 | 279,306 | 46 |

Audio exposes every indexed range. The other roots use up to three
first, middle, and last sample pages of at most 32 rows per page. The movies
index fits in one three-row page. Each page identifies its row span and each
root lists the full index path. The HTML contains 2,208 rows (797,094 bytes).

Range details display the archive-relative start and exclusive end. Verified
zlib rows join their manifest by both endpoints and include the extracted file
path and SHA-256. Levels and movies are index-only. Unclassified ranges show
`Unresolved`, and ranges without manifest rows show
`No extracted file is listed for this range`. Pack membership remains at
archive level.

## Chromium validation

```sh
NODE_PATH=/home/lynxnathan/.npm/_npx/e41f203b7505f1fb/node_modules \
  node tools/verify_extraction_index_pilot.cjs
```

The Playwright check opens the local HTML and drills into a range and back to
the root for every archive. It checks the sample limits, full audio coverage,
unresolved audio and movies ranges, and no-file details for levels and movies.
It verifies the audio hash at `0x5000..0x6316` and the anim hash at
`0x6000..0x62dc`. The latter is
`cbdb4e9d1ecbe7ff0a197f759c47c0c5f0f88ebb0830ee6af958ef6949b430e4`.

Artifact: `output/extraction-index-pilot/index.html`.
