# Script workstream status

## Done

- Restored the direct-inotify bus wait/tail in `17cc1c2`; stopped the daemon and
  kept the terminal-vs-status digest fix. No bus polling is active.
- Decoded the generic 48-byte array header: used count at `+0x14`, stride at
  `+0x18`, element type hash at `+0x28`.
- Matched `0xc92cdeca` to `JOAAT("vector3")`; validated 7,960 typed arrays (including empty arrays).
- Decoded the class-0 bone hierarchy and flattened 3,043 bones across 44 roots.

## Artifacts

- `handoff/audio-awc.md` — AWC extraction report (6,625 containers / 22 GB;
  codec blocked).

- `handoff/extraction-coverage-summary.tsv` — all 8 archives full; 86,029
  ranges / 1,096,854,128 stored / 1,896,307,661 decoded / 429,764,784
  unclassified.
- `handoff/unclassified-summary.tsv` / `unclassified-gaps.md` — 6,111 spans,
  largest gaps by archive.
- `handoff/extraction-entry-verification.tsv` — six PASS cases across script,
  data, common, and story archives.
- `handoff/anim-index-pilot.md` — anim.rpf 100% index; Rust 4.34 GB RSS;
  stream_index 333 MB / 29s / 130,510 zlib; 20.58 MB stream missed by the
  Rust 16 MiB cap.
- `handoff/remaining-archive-index.md` / `remaining-archive-index-summary.tsv`
  — all 8 indexes: 157.76 GB stored, 360.57 GB decoded, 96 streams >16 MiB.
- `handoff/bulk-extraction-status.tsv` — packs 144,366 streams / 9.74 GB decoded.
- NVMe extraction root: `output/extracted/{packs,anim}`; packs 144,366 and anim
  130,510 streams, both PASS; manifests point at the local root.
- `handoff/bulk-extraction-verification-summary.tsv` — packs PASS, 0 missing /
  0 extra / 0 failures.
- `handoff/packs-signature-summary.tsv` — 144,366 streams classified; dominant
  `u16_4042` 28,713 / 5.43 GB.
- `handoff/packs-4042-probe.md` / `.tsv` — 2,992 sizes; 64 KiB classes; header
  low-byte type-tag hypothesis.
- `handoff/packs-4042-classes.md` — metadata/high-entropy/structured size regimes.
- `handoff/packs-0f000080-probe.md` / `.tsv` — 1,148 compact ~10 KiB
  high-entropy streams; geometry/animation hypothesis.
- `handoff/packs-binary-clusters.md` / `.tsv` — 113,480 binary streams / 32
  ML clusters; proposal engine only.
- `handoff/packs-label-queue.tsv` — 128 representative samples / 32 clusters
  for the operator's labels.
- `handoff/remaining-archive-index-verification.tsv` / `...-sha256.tsv` — 8/8
  coverage PASS; hashes for all 184 MB of local indexes.
- Canonical source: `CORPUS`
  (22 RPF9 / 161,307,137,472 bytes; 619 GB free).
- `handoff/downloads-corpus-inventory.tsv` — 22 RPF9 / 161,307,137,472 bytes;
  14 verified / 3,542,353,632 source bytes; six smaller packs verified by
  integrator in `f37b99f`.
- `tools/extraction_tree.py` / `output/general-extraction/index.html` —
  integrator containment view (8 archives, 86,029 ranges, 36,640 files).
- `handoff/script-quadtree-summary.tsv` — 44 roots / 3,007 items.
- `handoff/script-quadtree-verification.tsv` — 8/8 PASS.

- `handoff/script-bones.tsv` — 3,043 rows: root, table, bone hash, bone node,
  point array, point count, first point and ID.
- `handoff/script-bone-points.tsv` — 15,732 rows: every point/edge entry with
  two vec3 slots, ID, and point/edge/zero classification.
- `handoff/script-bone-geometry.tsv` — 3,043 rows: centroid, bounds, extents,
  point/edge counts.
- `handoff/script-bone-templates.tsv` — exact bone-hash groups.
- `handoff/script-bone-template-families.tsv` — 16 near-identical families.
- `handoff/script-vehicle-curves.tsv` — 1,935 vehicle mover curves with key
  hash, JOAAT name when known, and t/y/z ranges.
- `handoff/script-vehicles.tsv` — 385 vehicle-like roots, names, curve counts,
  and channel coverage.
- `handoff/script-vehicle-curve-join.tsv` — same-root key/name/part/rotation
  diagnostics for all 1,935 curves.
- `handoff/script-vehicle-branch-relations.tsv` — branch endpoints for the
  known windows and the four unnamed channels on astron/216cstreamer/airbus.
- `handoff/script-vehicle-curve-quantization.tsv` — native-precision grid and
  leaf-permutation diagnostics; the angular hypothesis is unverified.
- `tools/bone_table.py`, `tools/bone_geometry.py`, `tools/bone_templates.py`,
  `tools/vehicle_curves.py`, `tools/vehicle_bone_names.txt`,
  `tools/bone_template_families.py`, `tools/array_types.py`, `tools/type_tags.py`,
  `tools/value_entries.py`, `tools/value_array_context.py`,
  `tools/transform_pairs.py`.
- `investigation.md` and `plan.md` are current.

## Worktree state

- Only `main` remains. `investigate/script-graph` and `investigate/data-rpf` are
  archived as tags; the data worktree tarball is
  `ARCHIVE/data-worktree-20261120T203324.tar.gz`
  with sha256 `cb2a87c9…e25e9`.

## Needs

- The hash algorithm or a name crib for the 612 class-0 bone-table hashes.
- A model-to-layout or bone-order mapping from `data.rpf` to align the tables.
- A decision on the high-1/high-2 pairs in the `0x1ebb416b` entries.
- Data-side mapping for request `#0067`: **negative** (`#0071`), 0/44 roots and
  0/612 hashes against 2,502 resource names and 3,212 PSIN names. Evidence in
  `handoff/data-skeleton-family-links.tsv`.
- Four vehicle-curve channels are **parked**; names/units open. Data returned to
  direct-inotify standby in `#0081`.
- `0xb1ee00d0`: 186 arrays / 4 roots / 294 entries; a 48-byte sibling layout
  with the vec3 at `+0x10`; names open.
- `0x8f18aff0`: 2,491 normalized weight arrays (7,630 pairs); every array sums
  to 1.0; 252 hashes, 57 shared with the bone table.

## Next

- Name or align the 612 table hashes; then join the 3,043 bones to the data bone
  corpus and vehicle layouts.
- Decode the remaining typed arrays (`0xb066759f`, `0xb1ee00d0`) at field level.
- Return to Front A only with independent framing, key material, or a decoded
  field.
