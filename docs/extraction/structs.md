# Serialized structs across the corpus

Most entry payloads open with a serialized container struct: eight 4-byte slots
whose values are `0x5`-tagged **self-relative pointers** (`0x50000080` = tag 5,
offset `0x80`), one `0x6`-tagged field, and `{ptr, u16 count, u16 capacity}`
array headers. The scanner identifies a struct when the first `0x40` bytes (at
offset 0, or after a 256-byte payload header) hold at least two such pointers,
where a candidate is a `u32` with upper nibble `5..0xA` and low four bits zero.

Guardrails learned the hard way:

- scan the **header only**; whole-payload scanning invents dozens of pointers
  per 6 MB body;
- `+0xa0` is a **bvh4 class field**, not a container field — it is harvested only
  when the record is 208 bytes and carries the full bvh4 pointer table
  (`0x50000080/a0/b0/c0/50`, `1` at `+0x10`, `0x60000000` at `+0x20`);
- **tag-5 targets need not stay inside the stream.** `core_bvh4`'s descriptor
  points inside its own 208 bytes, but `navmeshes` structs point far outside
  (a 1,840-byte body holds `0x53149a19`, target `0x3149a19`). Requiring an
  in-body target rejected 2,446 of 2,447 navmeshes structs; alignment alone is
  the correct filter, and the shares in the table below are therefore lower
  bounds for archives whose pointers leave their stream.

## Corpus map

`handoff/struct-summary.tsv` (tool: `tools/struct_harvest.py`), from a
seeded **random** 200-stream sample per archive — strided sampling is biased
because struct streams cluster in long runs.

| Archive | Streams/entry | Struct share | Top tag | Tag-5 share | External ptrs | Implied attach |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `anim` | 1.541 | 71 % | 5 | 85 % | 0.577 | 0.541 |
| `audio` | 0.117 | 15 % | 10 | 10 % | 2.8 | -0.883 |
| `common` | 2.282 | 19 % | 7 | 0 % | 2.184 | 1.282 |
| `core_bvh4` | 1.924 | 52 % | 6 | 8 % | 0.923 | 0.924 |
| `core_licenses_data` | 0.6 | 100 % | 7 | 0 % | 2.0 | -0.4 |
| `core_restofworld` | 2.069 | 56 % | 5 | 85 % | 0.304 | 1.069 |
| `core_restofworld001` | 1.222 | 85 % | 5 | 82 % | 0.321 | 0.222 |
| `data` | 1.238 | 78 % | 5 | 82 % | 0.568 | 0.238 |
| `levels` | 2.131 | 43 % | 5 | 78 % | 0.776 | 1.131 |
| `navmeshes` | 1.395 | 62 % | 5 | 100 % | 0.0 | 0.395 |
| `packs` | 1.795 | 49 % | 5 | 92 % | 0.173 | 0.795 |
| `script` | 1.042 | 4 % | 10 | 0 % | 2.286 | 0.042 |
| `shaders` | 1401.667 | 18 % | 7 | 8 % | 2.861 | 1400.667 |
| `shared_minigame000` | 1.619 | 52 % | 5 | 74 % | 1.219 | 0.619 |
| `shared_minigame000_bvh4` | 1.935 | 45 % | 6 | 4 % | 0.956 | 0.935 |
| `story000` | 0.884 | 70 % | 5 | 84 % | 0.695 | -0.116 |
| `story000_bvh4` | 1.0 | 100 % | 7 | 0 % | 2.0 | 0.0 |
| `story000_restofworld` | 1.276 | 76 % | 5 | 91 % | 0.371 | 0.276 |
| `story000_script` | 0.858 | 24 % | 8 | 0 % | 3.771 | -0.142 |
| `textures` | 2.011 | 44 % | 5 | 93 % | 0.18 | 1.011 |

`movies`, `appdata0` have no zlib streams.

## What the map says

- **Tag 6 is the `*_bvh4` signature.** Both bvh4 archives show tag 6 as the
  dominant segment nibble, exactly one external pointer per struct, and that
  count matches the archive's implied attachment ratio (0.93 vs 0.92 and
  0.98 vs 0.94). No other archive has this profile.
- **Tag 5 dominates elsewhere** (82–99 % of structs in `anim`, `data`, `levels`,
  `navmeshes`, `packs`, `story000`, `textures`): those structs address only
  in-stream sub-structures.
- **Segment tags 7–10 mark the script/audio family**: `script` (tag 10, 4.0
  external/struct), `story000_script` (tag 8, 3.6), `audio` (tag 10, 2.4),
  `common` (tag 7, 2.0), `shaders` (tag 7, 2.7).
- **Struct share tracks entry density**, not archive size: `data` (79 %) and
  `anim` (78 %) are nearly all struct roots, `script` is 1 % (its payloads are
  the object graph), and `levels` (57 %) sits mid-range because its large packs
  hold many data streams per struct.
- The external-pointer count is **not** an attachment counter outside `*_bvh4`:
  distinct-target counting on 2,500 `levels` streams gives 0.54 against 1.13
  implied. The reliable universal proxy is the **struct-root count per pack**,
  which reproduces declared N to ±3 across sampled small `levels` packs.

## Reproduce

```sh
python3 tools/struct_harvest.py \
  --archives levels.rpf:output/index/levels.tsv core_bvh4.rpf:output/index/core_bvh4.tsv \
  --sample 100
```
