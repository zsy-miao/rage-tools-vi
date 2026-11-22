# Plan

Live check/todo list. Evidence, measurements and the failures that led here belong
in [investigation.md](investigation.md) and `handoff/`; completed work is one line
of state, not a log.

Last updated: 2026-11-23 (script metadata format recovered from the writer).

## Current state

- **Corpus:** 22 archives indexed — 4,415,868 ranges / 161.3 GB stored / 365.0 GB
  decoded; every index tiles its archive. Source archives mirrored to local NVMe
  (`/home/lynxnathan/gta6-source`), verified by size/mtime on every path and by
  hash on a sample.
- **Entries:** one corpus pass (4 min, parallel) fits an entry model per pack and
  emits payload-derived manifests for 14 archives — **188,298 entries**, exact
  count verification (`--tolerance 0`). `core_bvh4` reproduces the declared count
  for 1,253 of 1,261 packs.
- **Audio:** complete — 93,344 Opus + 1,818 XMA2 + 73 ACE1 streams, 0 failures;
  `frames × channels / declared` never below 1.0.
- **Script schema:** chunk chain `PSIN→LSCH→LENM→LSNS→LGID→LRSC` recovered from
  the writer `FUN_144083410`; 1,012/1,012 records parse exactly. 63,288 typed
  rows with the type word at `+0x0c`; 42 % of rows name their property (164
  properties, 14,530 keys). `levels` uses the same chain with a tagged section bag
  (209 tags) plus a `CHKS` trailer. `LSNS` 58,697 sixteen-byte records.
- **Names:** one registry, 36,952 hash→name pairs with confidence and an
  ambiguity flag for JOAAT collisions; every handoff table annotated (4.3 % of
  hash values named corpus-wide, concentrated in bones and the script schema).
- **GPU:** shader decompilation is a separate repository, `rdna2-spirv/`.
- **Health:** `tools/check.sh` (tests, index invariants, shader suite, docs build).
- **Executable:** `game_scarlett_master.exe` obtained (sha256 `e95020b2…8993`,
  120,181,760 B, PE32+ x86-64, timestamp 2026-11-13). Authentic, not a launcher:
  `.xbld`/`.retplne`/`.voltbl` sections and imports of `d3d12_xs`, `xg_xs`,
  `xmem`, `xapu`, `AcpHal`, `XCRDAPI`, `XboxBvhBuilder`, `Bink2Scarlett`.
  Harness: `tools/pe_audit.py`, `tools/pe_scan.py` (correct PE section mapping),
  and Ghidra headless with `cache/ghidra/Target.java` (decompile) and
  `Refs.java` (references). Two analysed databases exist: the fast `-noanalysis`
  project and a full-analysis project in `cache/ghidra_full`. Never pass
  `-deleteProject` when the point is to keep the result.

## Now

- [x] Script metadata format recovered from the writer `FUN_144083410`: chain
  `PSIN→LSCH→LENM→LSNS→LGID→LRSC`, each `[magic][BE distance]`, payloads found by
  exact-fit count solving. 1,012/1,012 records parse; typed words agree with the
  heuristic scan to 0.6 %. `tools/script_meta.py`.
- [x] Decode the five `PSIN` blocks: typed rows (63,288, type at `+0x0c`),
  a 5-entry sub-table directory, a struct block, a 16-byte-row block and
  12-byte float triples. Field order corrected, `handoff/psin-rows.tsv` written;
  42 % of rows now have a named property (`tools/psin_blocks.py`).
- [x] Downstream PSIN artifacts regenerated with the corrected pairing
  (`entries`, `segments`); entry count unchanged at 4,969, pairs now semantic
  (`Heading`+`Position` 2,807).
- [x] Remaining PSIN derivatives on the corrected pairing: `property tree` now
  reads through `script_meta`/`psin_blocks` (63,288 rows / 164 properties /
  14,530 keys), `table width` re-run with `--properties`.
- [x] `vocabulary` provenance settled: it is curated, not generated, and is now
  documented as such. A rule tried from the corrected rows produced 16 values
  against the curated 80, so regenerating it would be a regression.
- [ ] Settle whether the typed row's `c` word is a declaration index or a value:
  `Decay` carries a shared `300000` while byte rows count 0..6. Needs the script
  data section.
- [x] **Correction:** `CHKS` is a seventh chunk in *every* record, `script.rpf`
  included (1012/1012); the earlier "levels only" reading came from a magic table
  that did not list it yet.
- [x] `levels` records add a seventh chunk `CHKS`: `u32` big-endian record size
  (matches body length 60/60) plus an unidentified 4-byte tag. Chain census over
  3,000 records recorded.
- [ ] Identify the `CHKS` tag; ten 32-bit candidates (crc32, adler32, joaat32,
  fnv1a, murmur3, xxh32) over body, prefix and compressed stream are excluded,
  while the size field matches 80/80.
- [x] `levels` PSIN decoded as a tagged section bag: 209 tags over 400 records,
  descriptor count data-dependent (2..17+), `0xd56f1e2c` is its directory,
  `0x78ba5fa7` carries ASCII resource paths (`tools/levels_sections.py`).
- [x] Harvested 3,697 literal asset paths from levels sections `0x78ba5fa7`
  (2,965) and `0xec610df1` (732); joaat in 7 normalizations matches none of the
  name registry, the 14,530 PSIN keys or the 164 property hashes.
- [ ] Establish how levels paths are keyed: the strings exist but do not match
  any 32-bit table we hold, so either they are used literally or hashed by a
  function outside our set.
- [x] `LSCH` decoded as an index over `PSIN` sections: each 32-byte row starts
  with one of the record's section tags (200/200 records), and its sub-records
  carry a tag at `+0x0c`. `LENM` rows are the same shape in 24 bytes.
- [x] `LSCH` fields tested against both views on 4,901 sections: none is a count
  (`+0x18` matches block bytes only 36.7 %). The exact-fit solve stays the count
  oracle. Joined table at `handoff/script-sections.tsv`.
- [ ] Explain the 36.7 % partial match on the `LSCH` `+0x18` word — a computed
  length, not the literal block size.
- [ ] Identify the roles of `0x01393259`, `0x16` and `0xaeb623d8`.
- [x] Front region is not compressed (zlib/deflate/lzma/bz2), has no repeated
  keystream across 654 packs, and all regions ≥1 KB are H ≥ 7.79 (the earlier
  "174 low-entropy" reading withdrawn as a small-sample artefact).
- [x] Partial width law: 214/654 packs satisfy `size_b == align16(count * w)`
  with w in {8,10,12,16}, correlated with the mode word at `+0x20`; the other 440
  carry more than one table.
- [x] The 448 packs that fail the width law are composite: no header word works as
  a replacement count and `size_b/count` is scattered within a single mode.
- [ ] Find the second component's size law in composite packs — it is not a
  function of `count`.
- [x] 64-bit name hashes excluded from the front regions: 3,716,607 distinct u64
  words vs 886,848 candidates gives a chance floor of 4×10⁻⁸, and the observed
  count is zero — a clean negative, unlike the 32-bit test.
- [ ] 128-bit hashes, salted/seeded variants, and hash functions outside
  {joaat64, fnv1a64, murmur64a, murmur64a_seed1} remain open.
- [ ] Decide whether the RPF front region is **stored as-is** (a hash table) or
  decrypted above the archive layer. The full read→mount→entry-walk path
  (`0x140fc2540` → `0x141fb2600` → `0x1408ec210` → `0x1406bd160`) contains **no
  cipher call**, and the earlier "CBC" evidence was retracted — identical plaintext
  prefixes explain the predecessor statistic without a cipher.
- [x] Test the front region as a hash table: 7 hash functions × 20 name
  normalizations × 7.4 M words → flat ~560 hits per algorithm, i.e. chance.
  Excluded (`tools/front_hash_probe.py`).
- [x] Traced the consumer path in code: `FUN_141fb2600` copies the front region
  verbatim (header copy + file bytes), `FUN_14087aff0` computes a four-section
  arena layout from fields at `0x1a..0x2d`, `FUN_14087b0b0` sets `obj+0x38`.
- [ ] Identify the four front-region sections (p3×8, p4 bytes, p5×24,
  (p5-p6)×p7×p8 with p7 = declared entry count).
- [x] Archive class mapped: 147-slot vtable `0x1462fd480`; both factories
  (`+0x418`, `+0x420`) are methods of the archive itself, i.e. archives nest over
  sub-streams. `tools/vtable_scan.py` reproduces the slot count independently.
- [ ] Identify the stream class handed to the ctor (a bounded child stream) and
  read its `Read` at `+0x60`.
- [ ] Find the layer that produces the mapped buffer at `[stream+0x18]` /
  `[stream+0x20]` (the file object handed to the archive ctor). Full analysis is
  now available (`cache/ghidra_full`), so this is unblocked: start from
  `0x1428ce530` (mount-time, archive-only) and `0x140daed80` (codec dispatcher
  with three vtables, `0x1462fe720`/`740`/`760`).
- [x] `LSNS` table structure: `[path of ≤10 × 128-bit levels][per-script records]`.
  The path nests — 853 tables share level 1, 381 share all ten, 120 share the full
  path — so it encodes a hierarchy of script kinds, not a flat type id. Records are
  not sorted in any interpretation.
- [ ] What the per-script `LSNS` records contain. Within a kind the tail length is
  fixed (22–23, 19–20, 20–21) while every tail differs, so they are per-script
  values; contents remain opaque 128-bit words, and no word matches a name or a
  PSIN key.
- [x] `PSIN` tree segmented: `tools/psin_segments.py` splits a record where the
  table period changes. The four clean records come out as one leaf each (width
  4×3, 6×1); record `1054` decomposes into widths 2/4/4/6/2 plus flat spans.
  371 table leaves and 5,015 flat over 849 records.
- [ ] What the widths mean (2 = an `Id`/`Type` pair list, 4 and 6 wider records).
- [ ] Name the remaining ped-rig bones and weight hashes. The 174k-token corpus
  sweep is exhausted (4 bone candidates, 1 weight candidate, both unverified);
  this needs a new vocabulary source, not a wider search.
- [x] `movies.rpf` indexed: 515 Bink2 containers covering **99.993 %** of 8.8 GB
  (425,440 frames); payload size at `+0x04`, container is `align(0x800, size)`.
- [x] `core_restofworld`: 1,241.7 MB unclassified, and the largest span holds a sorted
  table of **1,020 `{u24 offset, u8 tag}` entries** at `+0x1000` (96.2 % monotonic).
- [x] Swept every archive's largest `unclassified` span (`tools/unclassified_probe.py`);
  two open with a sorted `u24` table (`core_restofworld` 97.5 %, `story000_restofworld`
  96.6 %), two are strongly *non*-ascending (`shared_minigame000` 22.6 %, `story000`
  18.8 %) — descending or a different stride, not random.
- [x] `restofworld` spans have 4-byte-stride structure (~99 % ascending steps), but the
  **offset-table reading is retracted**: four base candidates give ≤3/998 structural
  hits, the small values `30/1080/1364/1920` recur in both archives, and there is no
  DDS/PNG/RSC7 magic. Five interpretations tested and excluded.
- [x] `restofworld` descriptor **is a Bink2 header** (`KB2n` at `+0x927` / `+0xccf`), and
  both archives index as movie archives: `core_restofworld` 11 movies / 95.814 %,
  `story000_restofworld` 7 movies / 60.595 %. Classified share 4.17 → 99.98 % and
  34.70 → 95.29 %.
- [x] The `[1] == [3]` mystery is Bink2 storing the frame count twice (`+0x08`, `+0x10`),
  as already measured in `movies.rpf`.
- [x] Bink2 indexed beyond the movie archives: `story000` **264 movies / 3.33 GB** (its
  classified share goes 35.39 → **98.02 %** with the ADAT and Bink side indexes).
- [ ] What `[0]`, `[1] == [3]` and `[2]` measure, and whether the payload after the
  descriptor is Bink2 (the `movies.rpf` header has the same width/height/fps shape).
- [ ] What the 16 MiB window holds, and what the tags mean (mostly `0`; `1` in 214
  entries of `core_restofworld`, absent in the other).
- [ ] Explain the two non-ascending spans (descending order or another stride).
- [ ] Entry model for `levels` (728 of 2,044 packs exact). The failures are
  systematic — about five non-entry struct streams and ninety surplus data
  streams per pack, i.e. entries owning several data streams. Needs the
  entry-type distribution.
- [x] Extraction browser rebuilds for every archive; a missing verification row is
  shown as "indexed only" instead of failing the build.

## Next

- [x] Variant-aware ADAT index: `audio.rpf` is **99.485 %** indexed as ADAT
  (7,153 banks), one rule for `0xff21` and `0xff02`, table ending at `header_size`.
- [x] `audio.rpf` is **99.687 %** indexed as ADAT (7,159 banks). Three rules cover
  the variants: computable table position, suffix scan for `0xff25`/`0xff61`, and a
  suffix-scan fallback when the computed rule does not close.
- [ ] The residual 0.313 % of `audio.rpf`: 19.5 MB front region plus 70 MB where
  `ADAT` bytes do not validate as a container at any offset shift.
- [x] Full AWC census: **70,484 containers / 1,819,816 streams / 28.53 GB** of stream
  data across `audio.rpf` and `story000.rpf`; XMA2 count matches the decoded total
  exactly, Opus decode covers 5.2 % of what exists.
- [x] First decode from a previously untouched `0xff02` container: Opus mono, 124
  packets, 2.48 s, non-silent; declared rate 32 kHz is the *source* rate, decode at
  48 kHz (`tools/decode_adat_stream.py`).
- [x] Decode sample across variants: 112 streams / 5.8 min / 0.13 FS median RMS;
  `0xff02`, `0xff21` and `0xff61` decode, `0xff25` does not fit the 8-byte record
  model (count 2, header 64, three non-chunk records per stream).
- [x] `0xff25` identified as an **inline-descriptor** variant, not a table: 95.3 % of
  600 containers carry `80 bb` (48 kHz) + codec + channels; 401 stereo / 171 mono Opus.
- [x] Acoustic search (`tools/probe_ff25_payload.py`) decodes `0xff25` payload: LE `u16`
  packets from `+0x1060` at flatness 0.0022, candidate starts 82 bytes apart; small
  containers give only weak 8–12 packet hits.
- [x] `0xff25` **solved**: blocks of `0x800`, payload at `block + 0x60`, ~24 packets per
  block; 3,049 packets decode to 60.98 s stereo per 266 KB container (~50 h corpus-wide).
  `tools/decode_adat_stream.py --ff25`.
- [ ] Decode the `0xff25` corpus (~50 h of audio) now that the framing is known. Established: body is audio
  (H 7.74–7.79), `header_size` is **not** the data offset, no table under any byte shift,
  no size field in the first 64 bytes, fields sit at odd offsets (three independent
  signs), payload is packet-framed (1,678 short runs) but **not** `0x800`-block framed.
  Payload not block-framed at six sizes × four shifts; chains stop after 12–25 packets;
  `+0x860` is a documented `a0 00 f8` marker region; BE-`u16` and LE-`u32` prefixes fail.
  A `a0 00 f8` marker-record form exists in 17/120 sampled containers: records of exactly
  162 bytes starting at `+0x860`, body high-entropy. The variant may cover more than one
  sub-layout.
- [x] Decode throughput measured: **79 streams/s**, so the remaining 1.79 M Opus streams
  are ~6.3 h of compute — but ~0.45 TB of PCM against 188 GB free.
- [ ] Choose the bulk-decode output form (lossless re-mux/FLAC vs stream-and-measure vs
  a larger volume) before running the 6.3 h pass.
- [ ] Decode the remaining ~1.7 M Opus streams (5.2 % covered so far).
- [x] `levels.rpf` KB2 scan: 719 candidates, **0** valid containers (462 bad version byte,
  257 bad dimensions) — the raw `KB2` matches there are coincidence, and the pass is
  recorded as a negative rather than an empty index.
- [x] `shaders.rpf`: largest span begins with an `SGD5` header at `+0x9000` (only 2 in the
  archive), no `DXBC`/`DXIL`/`SHDR` magic, entropy 6.83 — raw program data, no per-shader
  boundary yet.
- [x] First content-level validation: the decoded `0xff02` stream has spectral flatness
  **0.0051** (1.0 = white noise), so it is programme material, not a framing artefact.
  Bink2 movies cannot be content-checked: `ffmpeg` has no decoder for this `KB2` variant.
- [ ] Give every decode path one content check (flatness for audio, pixel stats for
  images, frames vs declared for video) before calling it working.
- [ ] ACE1 trailer pairs (15 u32 fields; 73 streams, all decoded).
- [ ] Map the script type/class IDs and transforms.
- [ ] Resolve the unnamed object roots.
- [ ] Packs active-learning queue.
- [ ] Script object root field roles.

## Blocked

Each needs a specific input, not more effort.

- [ ] RPF9 table of contents — content unidentified. `Front B` *is* a per-entry
  table for 206 of 654 packs (`size_b == align16(count * w)`, w in 8/10/12/16) and
  composite for the other 448; no 32-bit hash of 36,952 names appears in either
  region; the traced read→mount→entry-walk path holds no cipher. Wide (64/128-bit)
  hash layouts stay open because they are statistically indistinguishable from
  random bytes. Every entry here is payload-derived.
- [ ] Transform, if any, sits in the *stream's* `Read` (`+0x60`): the archive
  layer copies both buffers verbatim (`FUN_141fb2600`), so AES/CNG/Blowfish
  exclusions apply to the image as a whole, not to this link. Reading the stream
  implementation is the remaining step.
- [ ] Front A milestone on `story000_bvh4.rpf` — needs independent table framing.
- [ ] Exact end of the last `data.rpf` child — needs an independent trailer start.
- [ ] Multi-mip texture tail — needs a multi-mip dictionary.
- [ ] The 331,728-byte `script.rpf` blob — its size is not any single range in the
  index (largest is 0x52da0), so it needs locating before it can be parked or
  attacked.
- [ ] Script bytecode itself: not in a plaintext section. The executable is now in
  hand, so this is a code-tracing task, not a waiting task.
- [ ] Type-name vocabulary (`root_type`, `type_tag`): three vocabularies return
  nothing usable; most likely stored as text inside the masked data.

## Not mine

- [ ] `explorer/` — owned by another session.
