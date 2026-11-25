# Script schema (PSIN)

`script.rpf` records are not bytecode. Each record is a chain of chunks, and the
script schema lives inside them.

The format below is not inferred from the corpus. It was read out of the writer
in the executable — `FUN_144083410` — found by scanning `.text` for the chunk
magics, each of which occurs exactly once and all inside that one function. When
the recovered layout and the bytes disagree, the bytes win, and the checks below
are exact rather than statistical.

## The chunk chain

Every chunk is `[4-byte ASCII magic][big-endian u32: distance to the next chunk]`.
Nothing else is stored: no sizes, no counts, no terminator.

```
PSIN → LSCH → LENM → LSNS → LGID → LRSC
```

Every record ends with a seventh chunk, `CHKS`. The order is fixed.

Two traps cost us real time and are worth naming:

- The header word is **big-endian** while the payload words are little-endian.
  That is why an old helper that read a big-endian size happened to work: the
  "size" it read *is* the distance to the next chunk.
- `0x4d4e454c` is **`LENM`**, not `LMEN`. A scan for the wrong spelling reports
  zero occurrences and looks like evidence that the chunk does not exist.

## Anatomy of one record

Record 42 of `script.rpf`, 5,392 bytes after decompression — the whole chain, with
each chunk's distance and payload size:

```
0x0000  PSIN  distance 0x0d60  payload 3,416 B  count 4 sections
0x0d60  LSCH  distance 0x01d8  payload   464 B  count 3 index rows
0x0f38  LENM  distance 0x0080  payload   120 B  count 1 index row
0x0fb8  LSNS  distance 0x04e4  payload 1,244 B  opaque table block
0x149c  LGID  distance 0x0008  payload     0 B  empty list
0x14a4  LRSC  distance 0x0058  payload    80 B  fixed header block
0x14fc  CHKS  distance 0x0014  payload    12 B  size + tag
0x1510  end of body
```

`0x14fc + 0x14 = 0x1510` — the chain ends on the last byte. Reproduce with:

```sh
uv run python tools/script_meta.py --index output/index/script.tsv --dump 1
```

## `PSIN`: the section table

```
+0x00  'PSIN'
+0x04  u32 BE  distance to LSCH
+0x08  count × 16-byte descriptors
          +0x00  u32  section tag
          +0x04  u32  payload length
          +0x08  u64  0xAAAAAAAAAAAAAAAA   (pointer, poisoned on disk)
       then each descriptor's payload, in order, each rounded up to 16 bytes
```

`count` is not stored. It is recovered by asking which value closes the
arithmetic exactly:

```
16*count + 0x10 + Σ align16(length_i)  ==  distance_to_next_chunk
```

The first payload starts at `16*count + 0x10` because the writer computes
`(16*count + 0x17) & ~15`, which rounds **down**. Using an ordinary round-up
alignment helper puts every payload 16 bytes late.

The `0xAA` runs that earlier scans treated as a terminator are these poisoned
pointers — the same trick appears as `0xEE` in `LENM` and `0xBB` in `LRSC`.

## The typed block

In `script.rpf` the sections are almost constant, five tags per record:

| tag | role | records |
| --- | --- | --- |
| `0x85b4c631` | typed rows | 1,012 |
| `0xde396fe2` | 80-byte sub-table directory | 1,012 |
| `0x01393259` | struct-like block | 1,012 |
| `0x16` | 16-byte rows, 128-bit material | 1,010 |
| `0xaeb623d8` | 12-byte `{u32, f32, f32}` triples | 855 |

The typed rows are 16 bytes each and the type word sits at the **end**:

```
struct PsinRow {          // 63,288 rows across 1,012 records
    u32 property;         // 164 distinct — Flags, Heading, Position, Name, Id, ...
    u32 key;              // 14,530 distinct — the object keys
    u32 value;            // value or reference, see the open question below
    u32 type;             // 0x101 int, 0x102 float, 0x103 hash, 0x104 bool, 0x105 byte
};
```

Type distribution across the corpus: byte 20,005 · float 15,277 · hash 14,739 ·
int 13,257 · bool 10.

### Correction: an earlier extraction was shifted by 8 bytes

The first extractor sliced each record at `offset + 8`, which put its 16-byte grid
8 bytes early. Its `type` column was therefore the real `+0x0c` word — correct by
accident — but its `property` and `key` columns came from the *next* physical row.
Values were being paired with the following row's property.

Fixing the alignment changed what the data looks like: property coverage went from
4.3 % of rows named to **42 %** (26,893 of 63,288), and the dominant entry pair
became `Heading` + `Position` (2,807 pairs), which is what a flattened placement
schema should look like.

## `LSCH`: the index over sections

`LSCH` rows are 32 bytes and *name the sections*:

```
+0x00  u32  section tag          <- one of this record's PSIN tags (200/200 records)
+0x04  u32  hash
+0x08  u32  small value
+0x0c  u32  zero
+0x10  u64  pointer              <- poisoned 0xAA on disk
+0x18  u32  value
+0x1c  u16  zero
+0x1e  u16  sub-record count
       then sub-records, 16 bytes each, appended after the rows
```

Sub-records carry a tag at `+0x0c`, so the record cross-references itself twice.
`LENM` rows have the same shape in 24 bytes (`tag`, `hash`, poisoned pointer,
`u16` sub-count at `+0x10`).

None of the index fields is a count of its section: tested against both the block
byte length and the row count over 4,901 sections, the best agreement is 36.7 %,
which is a computed length rather than the literal size. The exact-fit solve stays
the only count oracle.

## `levels` records look different

Same chain, different content: a `levels` PSIN is a bag of tagged sections. Over
the first 400 records there are **209 distinct tags**, and the descriptor count
varies from 2 to 17+ depending on what the level contains. `0x78ba5fa7` and
`0xec610df1` carry NUL-padded ASCII resource paths, for example
`acaidreams_protectedarea/all.pso.meta` — 3,697 distinct paths across 6,982
records.

## `CHKS`

Twelve bytes: a big-endian total record size (matches the decompressed body length
in 60/60 records) followed by a 4-byte tag not yet identified. Candidates
joaat32, fnv1a, crc32 and adler32 over the body, the body prefix and the
compressed stream are all excluded.

## Artifact provenance

`handoff/psin-rows.tsv` (63,288 rows) and `handoff/script-sections.tsv` (4,901
sections) are generated — by `tools/psin_blocks.py --rows` and
`tools/script_sections.py` respectively. `handoff/psin-vocabulary.tsv` is **curated
by hand**: it lists named PSIN values grouped by a lower-cased English property
name (`flag`, `name`, `weapon_group`, `vehicle_class`), and no rule tried so far
reproduces it from the rows alone. Treat it as a vocabulary table, not as output,
and do not overwrite it from a script.

## Running the parser

```bash
# whole corpus, chain census and a decoded sample
uv run python tools/script_meta.py script.rpf --index output/index/script.tsv --dump 1

# the five sections side by side, corrected field order
uv run python tools/psin_blocks.py --index output/index/script.tsv --show 1

# joined PSIN + LSCH view
uv run python tools/script_sections.py --out handoff/script-sections.tsv

# levels section census and path harvest
uv run python tools/levels_sections.py --archive "$SRC/levels.rpf" \
    --index output/index/levels.tsv --limit 400
uv run python tools/levels_paths.py --archive "$SRC/levels.rpf" \
    --index output/index/levels.tsv
```

Validation: **1,012 / 1,012** records produce the complete seven-chunk chain, and
the chain covers each decompressed body **exactly** — the last chunk's distance ends
on the final byte, with zero slack. That is the check that would have caught an
unlisted magic: a missing chunk type would leave the body longer than the chain. It
is enforced by `tools/script_meta.py --verify`, and the earlier six-chunk reading in
an earlier reading fell into exactly that trap, and the typed-word count agrees with the olderer independent
heuristic scan to 0.6 % (63,290 vs 62,910).

## Open questions

- What the `value` word means. It is mostly the declaration index (0, 1, 2, ...)
  but `Decay` appears six times with a shared `300000` inside the same block, so
  it is either a value or a reference, and both cases coexist. Settling it needs
  the script data section.
- The roles of `0x01393259`, `0x16` and `0xaeb623d8`.
- Why the `LSCH` `+0x18` word matches the block size 36.7 % of the time.
- The `CHKS` tag.
- How `levels` paths are keyed: the strings exist, but joaat in seven
  normalizations matches none of the 36,952 names, the 14,530 PSIN keys or the 164
  property hashes.
