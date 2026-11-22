# Handoff tables

Every table here, its size, and where it comes from. Rendered from
`handoff/provenance.tsv` by `tools/handoff_manifest.py`; that manifest is the
source of truth and is checked by `tools/check.sh`.

**120 tables** — 111 generated, 4 curated, 5 legacy, 0 unclassified.

## Curated (hand-maintained)

| file | rows | why |
| --- | ---: | --- |
| `bone-hash-names-curated.tsv` | 60 | bones confirmed by hand against geometry |
| `names.tsv` | 36,952 | JOAAT names from CodeWalker meta plus harvested corpus |
| `packs-label-queue.tsv` | 128 | work queue, not a derived result |
| `psin-vocabulary.tsv` | 80 | named PSIN values grouped by hand |

## Generated

| file | rows | cols | producer |
| --- | ---: | ---: | --- |
| `archive-inventory-summary.tsv` | 33 | 5 | exact name in a tool |
| `audio-ace1-decode.tsv` | 73 | 13 | exact name in a tool |
| `audio-awc-framing.tsv` | 2,320 | 18 | exact name in a tool |
| `audio-census-totals.tsv` | 9 | 5 | exact name in a tool |
| `audio-full-census.tsv` | 7,159 | 7 | exact name in a tool |
| `audio-full.tsv` | 95,162 | 10 | exact name in a tool |
| `audio-gap-census.tsv` | 534 | 7 | exact name in a tool |
| `audio-opus-decode.tsv` | 2,081 | 16 | exact name in a tool |
| `audio-opus-trim-model.tsv` | 2,081 | 10 | exact name in a tool |
| `audio-story000-census.tsv` | 63,325 | 7 | exact name in a tool |
| `audio-variant-decode.tsv` | 4,704 | 9 | exact name in a tool |
| `audio-xma2-decode.tsv` | 166 | 10 | exact name in a tool |
| `bone-hash-names.tsv` | 99 | 4 | exact name in a tool |
| `bulk-extraction-status.tsv` | 1 | 9 | tool name appears in the table name: tools/bulk_extract.py |
| `bulk-extraction-verification-summary.tsv` | 2 | 7 | exact name in a tool |
| `core-bvh4-descriptors.tsv` | 269,106 | 15 | family: bvh4 descriptor manifests |
| `core-bvh4-entries.tsv` | 294,614 | 10 | exact name in a tool |
| `corpus-pass.tsv` | 22 | 9 | exact name in a tool |
| `data-entries-chains.tsv` | 6,537 | 8 | family: entry reconciliation |
| `downloads-corpus-inventory.tsv` | 108 | 4 | family: inventory reports |
| `entry-reconciliation.tsv` | 22 | 7 | exact name in a tool |
| `extraction-coverage-summary.tsv` | 8 | 8 | exact name in a tool |
| `extraction-entry-verification.tsv` | 6 | 8 | exact name in a tool |
| `extraction-inventory-summary.tsv` | 127 | 6 | exact name in a tool |
| `header-census-full.tsv` | 4,373 | 10 | exact name in a tool |
| `header-census.tsv` | 71 | 10 | stem in a tool: header-census |
| `header-words.tsv` | 4,373 | 34 | tool name appears in the table name: tools/header_words.py |
| `index-coverage.tsv` | 22 | 6 | exact name in a tool |
| `name-coverage.tsv` | 27 | 7 | exact name in a tool |
| `navmeshes-entries-chains.tsv` | 25,981 | 8 | family: entry reconciliation |
| `navmeshes-entries.tsv` | 2,447 | 8 | family: entry manifests (tools/corpus_pass.sh) |
| `pack-extents-leaves.tsv` | 45 | 6 | tool name appears in the table name: tools/pack_extents.py |
| `pack-extents-textures.tsv` | 21 | 9 | tool name appears in the table name: tools/pack_extents.py |
| `pack-model-fit.tsv` | 3,467 | 7 | exact name in a tool |
| `packs-0f000080-probe.tsv` | 62 | 3 | exact name in a tool |
| `packs-4042-classes.tsv` | 20 | 5 | exact name in a tool |
| `packs-4042-probe.tsv` | 64 | 3 | exact name in a tool |
| `packs-binary-clusters.tsv` | 32 | 8 | exact name in a tool |
| `packs-signature-summary.tsv` | 8 | 3 | exact name in a tool |
| `psin-entries.tsv` | 4,969 | 6 | exact name in a tool |
| `psin-names.tsv` | 544 | 5 | exact name in a tool |
| `psin-rows.tsv` | 63,288 | 7 | exact name in a tool |
| `psin-segments.tsv` | 5,496 | 5 | exact name in a tool |
| `remaining-archive-index-summary.tsv` | 8 | 10 | family: report summaries |
| `rig-names-corpus.tsv` | 12 | 6 | exact name in a tool |
| `script-array-inventory.tsv` | 7,960 | 10 | exact name in a tool |
| `script-bone-geometry.tsv` | 3,043 | 20 | exact name in a tool |
| `script-bone-namespace-probe.tsv` | 16 | 13 | tool name appears in the table name: tools/script_bone_namespace_probe.py |
| `script-bone-points.tsv` | 15,732 | 15 | exact name in a tool |
| `script-bone-template-families.tsv` | 16 | 11 | exact name in a tool |
| `script-bone-templates.tsv` | 38 | 5 | exact name in a tool |
| `script-bones-named.tsv` | 3,043 | 17 | exact name in a tool |
| `script-bones.tsv` | 3,043 | 14 | exact name in a tool |
| `script-pair-arrays.tsv` | 7,630 | 9 | exact name in a tool |
| `script-quadtree-summary.tsv` | 44 | 8 | exact name in a tool |
| `script-quadtree-verification.tsv` | 8 | 3 | exact name in a tool |
| `script-sections.tsv` | 4,901 | 8 | exact name in a tool |
| `script-vehicle-branch-relations.tsv` | 23 | 8 | exact name in a tool |
| `script-vehicle-curve-join.tsv` | 1,935 | 8 | exact name in a tool |
| `script-vehicle-curve-points.tsv` | 6,298 | 10 | exact name in a tool |
| `script-vehicle-curve-quantization.tsv` | 147 | 7 | exact name in a tool |
| `script-vehicle-curves.tsv` | 1,935 | 12 | exact name in a tool |
| `script-vehicles.tsv` | 385 | 6 | exact name in a tool |
| `shared-minigame000-bvh4-descriptors.tsv` | 1,233 | 15 | family: bvh4 descriptor manifests |
| `story000-awc-framing.tsv` | 245 | 18 | exact name in a tool |
| `story000-awc-variants.tsv` | 2,952 | 14 | exact name in a tool |
| `story000-bvh4-control.tsv` | 4 | 8 | exact name in a tool |
| `struct-harvest.tsv` | 1,590 | 10 | exact name in a tool |
| `struct-summary.tsv` | 22 | 12 | exact name in a tool |
| `textures-entries-chains.tsv` | 25 | 8 | family: entry reconciliation |
| `textures-entries.tsv` | 1,349 | 8 | family: entry manifests (tools/corpus_pass.sh) |
| `unclassified-probe.tsv` | 21 | 9 | tool name appears in the table name: tools/unclassified_probe.py |
| `unclassified-summary.tsv` | 7 | 5 | exact name in a tool |
| `weight-hash-candidates.tsv` | 1 | 7 | exact name in a tool |
| `weight-hash-names.tsv` | 21 | 2 | exact name in a tool |
| `corpus-pass/entries-anim.tsv` | 5,826 | 8 | tools/corpus_pass.sh — per-archive entry manifests |
| `corpus-pass/entries-common.tsv` | 0 | 8 | tools/corpus_pass.sh — per-archive entry manifests |
| `corpus-pass/entries-core_bvh4.tsv` | 109,301 | 8 | tools/corpus_pass.sh — per-archive entry manifests |
| `corpus-pass/entries-core_restofworld.tsv` | 801 | 8 | tools/corpus_pass.sh — per-archive entry manifests |
| `corpus-pass/entries-core_restofworld001.tsv` | 0 | 8 | tools/corpus_pass.sh — per-archive entry manifests |
| `corpus-pass/entries-data.tsv` | 2,063 | 8 | tools/corpus_pass.sh — per-archive entry manifests |
| `corpus-pass/entries-levels.tsv` | 29,117 | 8 | tools/corpus_pass.sh — per-archive entry manifests |
| `corpus-pass/entries-navmeshes.tsv` | 23,530 | 8 | tools/corpus_pass.sh — per-archive entry manifests |
| `corpus-pass/entries-packs.tsv` | 15,983 | 8 | tools/corpus_pass.sh — per-archive entry manifests |
| `corpus-pass/entries-shaders.tsv` | 0 | 8 | tools/corpus_pass.sh — per-archive entry manifests |
| `corpus-pass/entries-shared_minigame000.tsv` | 210 | 8 | tools/corpus_pass.sh — per-archive entry manifests |
| `corpus-pass/entries-shared_minigame000_bvh4.tsv` | 128 | 8 | tools/corpus_pass.sh — per-archive entry manifests |
| `corpus-pass/entries-story000_restofworld.tsv` | 13 | 8 | tools/corpus_pass.sh — per-archive entry manifests |
| `corpus-pass/entries-textures.tsv` | 1,326 | 8 | tools/corpus_pass.sh — per-archive entry manifests |
| `corpus-pass/pack-model-anim.tsv` | 235 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-appdata0.tsv` | 0 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-audio.tsv` | 1 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-common.tsv` | 1 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-core_bvh4.tsv` | 1,261 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-core_licenses_data.tsv` | 1 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-core_restofworld.tsv` | 10 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-core_restofworld001.tsv` | 1 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-data.tsv` | 40 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-levels.tsv` | 2,044 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-movies.tsv` | 0 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-navmeshes.tsv` | 28 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-packs.tsv` | 59 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-script.tsv` | 2 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-shaders.tsv` | 1 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-shared_minigame000.tsv` | 44 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-shared_minigame000_bvh4.tsv` | 8 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-story000.tsv` | 419 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-story000_bvh4.tsv` | 1 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-story000_restofworld.tsv` | 16 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-story000_script.tsv` | 1 | 7 | tools/corpus_pass.sh — per-archive model fits |
| `corpus-pass/pack-model-textures.tsv` | 20 | 7 | tools/corpus_pass.sh — per-archive model fits |
