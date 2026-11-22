# Recovered structures

Every recovered structure, with how it was verified.
The **Status** column records which kind of evidence each row rests on.

| Status | Meaning |
| --- | --- |
| **code** | read out of `game_scarlett_master.exe`, verified line by line |
| **exact** | a count or size law that holds for every case measured, with the denominator given |
| **measured** | holds for most cases; the exceptions are counted |
| **open** | the field's role is not established |

---

## RPF9 header

The loader reads `0x10` bytes, checks the magic, then `malloc`s the region and
copies the header into it, so the first `0x10` bytes appear twice.

| Offset | Type | Meaning | Status |
| --- | --- | --- | --- |
| `+0x00` | `u32` | magic `9FPR` | code |
| `+0x04` | `u32` | size of buffer A → `malloc` argument | code |
| `+0x08` | `u32` | start offset of buffer B; `+0x04 − +0x08` is its size | code |
| `+0x0c` | `u32` | trailer length | exact, 4,373/4,373 |
| `+0x10` | `u64` | per-pack id | measured, unique across all 654 headers in the local mirror |
| `+0x1a` | `u16` | arena field `p3`: count of 8-byte records | code |
| `+0x1c` | `u32` | arena field `p4`: byte length of section 2 | code |
| `+0x20` | `u16` | arena field `p5`: count of 24-byte records; also `[family][format]` | code |
| `+0x22` | `u16` | arena field `p6`, subtracted from `p5` | code |
| `+0x24` | `u32` | entry count `N` | code |
| `+0x2c` | `u8` | arena field `p8`: 1 or 2, per-entry multiplier | code |
| `+0x2d` | `u8` | flags; bit 0 selects 16-byte instead of 4-byte section alignment | code |
| `+0x30` | `u32` | `+0x1c − 0x140` | measured, 4,306/4,373 |

## Archive object (in memory)

```
+0x00  vtable 0x1462fd480 (147 slots)     +0x28  arena descriptor
+0x08  file / stream object               +0x30  pointer to buffer A (the header)
+0x18  buffer A base                      +0x38  section 1 (p3 x 8 bytes)
+0x20  buffer A size
```

The lookup code reads `p3` from `[+0x30]+0x1a` and `p5` from `[+0x30]+0x20` — that
is, straight out of the copied file header — and `0x144e6f780` scans the 8-byte
records at `+0x38` comparing a `u16` key, returning `0xffff` for "not found".
So **section 1 is a small `u16`-keyed dispatch table searched linearly**, not a name
hash table. Status: **code**.

## Buffer A: the arena

`FUN_14087aff0` turns the header fields into five section offsets:

```
out[1] = align(base + 0x40)
out[2] = align(out[1] + p3 * 8)                    p3 records of 8 bytes
out[3] = align(out[2] + p4)                        p4 bytes
out[4] = align(out[3] + p5 * 0x18)                 p5 records of 24 bytes
out[5] = align8(out[4] + (p5 - p6) * N * p8)       (p5 - p6) * N * p8 bytes
```

For `data.rpf+0` (`p3=4, p4=336, p5=7, p6=1, N=699, p8=2`) the sections land at
`0x40..0x60`, `0x60..0x1b0`, `0x1b0..0x260`, `0x260..0x2328`.

The formula fits inside buffer A for **654 / 654** headers, which is what promotes
the field offsets from guess to code.

Past `out[5]` sits a fifth region carrying `N ×` a fixed per-pack size — exactly
`64` in 79 packs, `112` in 21, `48` in 12, and otherwise 48–68 bytes per entry. Its
bytes are high entropy (7.99) with no printable runs, so it is not a plaintext name
blob in this build.

Status: **code** for the formula and **exact** for the fit; **open** for what each
of the five regions contains.

## Buffer B: the entry table

A fixed-stride table, `align16(N × stride)`. For mode family `0x0001`
(2,908 of 4,373 headers) the stride is chosen by the `+0x2c` tag:

| tag | headers | stride | exact fits |
| --- | ---: | ---: | ---: |
| `0x00090f01` | 2,414 | 9 | 2,414 / 2,414 |
| `0x00090f02` | 494 | 10 | 494 / 494 |

Families `0x0002`–`0x0008` add a 16-aligned extra table
`S = size(B) − align16(stride × N)`, from 0 to 36,064 bytes.

Status: **exact** for family 1, **open** for the identity of `S`.

## Script metadata chain

`script.rpf` records are a chain of chunks, each
`[4-byte magic][big-endian u32: distance to the next chunk]`, emitted by
`FUN_144083410`:

```
PSIN → LSCH → LENM → LSNS → LGID → LRSC → CHKS   (all seven, in every record)
```

| Chunk | Payload | Status |
| --- | --- | --- |
| `PSIN` | `count` × 16-byte `{tag, length, 0xAA…}` then each payload, rounded up to 16 | code |
| `LSCH` | `count` rows of 32 bytes, then 16-byte sub-records | code |
| `LENM` | `count` rows of 24 bytes, then 16-byte sub-records | code |
| `LSNS` | opaque block of `distance − 8` bytes | code |
| `LGID` | `u32 count` then `count × 16` bytes; empty when `distance == 8` | code |
| `LRSC` | fixed `0x50`-byte block | code |
| `CHKS` | `u32` big-endian record size, then 4 unknown bytes | exact, 60/60 size |

The first `PSIN` payload starts at `16*count + 0x10` because the writer computes
`(16*count + 0x17) & ~15`, which rounds **down**. `count` is not stored; it is the
unique value that satisfies

```
16*count + 0x10 + Σ align16(length_i) == distance_to_next_chunk
```

Verified on the whole corpus: **1,012 / 1,012** records produce the complete chain.

## PSIN sections

| Tag | Role | Records |
| --- | --- | ---: |
| `0x85b4c631` | typed rows | 1,012 |
| `0xde396fe2` | 80-byte directory of five `(count, count, kind, 0)` entries | 1,012 |
| `0x01393259` | struct-like block with `0xffffffff` sentinels | 1,012 |
| `0x16` | 16-byte rows, 128-bit-looking material | 1,010 |
| `0xaeb623d8` | 12-byte `{u32, f32, f32}` triples | 855 |

`levels` uses the same chain with a *bag* of tagged sections instead: 209 distinct
tags over 400 records, descriptor count 2–17+. Status: **measured** for the
inventory, **open** for the roles of the last three tags.

## PSIN typed row

```
+0x00  u32  property   164 distinct
+0x04  u32  key        14,530 distinct
+0x08  u32  value      role open: declaration index or reference
+0x0c  u32  type       0x101 int, 0x102 float, 0x103 hash, 0x104 bool, 0x105 byte
```

63,288 rows. The type word is **last**; an earlier reader used `+0x04` and was
8 bytes misaligned, which paired every value with the next row's property.
Status: **code** for the layout, **open** for `value`.

## LSCH / LENM index rows

```
LSCH  32 bytes   +0x00 tag (one of this record's PSIN tags)  verified 200/200
                 +0x04 hash
                 +0x08 small
                 +0x10 u64 pointer, poisoned 0xAA on disk
                 +0x18 word  (matches block size only 36.7 % — a computed length)
                 +0x1e u16 sub-record count
LENM  24 bytes   +0x00 tag, +0x04 hash, +0x08 pointer (0xEE), +0x10 u16 count
```

Status: **exact** for the tag relation, **open** for the other fields. Of the
**4,901** sections in the corpus, **3,891** are indexed by `LSCH`; the 1,010 that
are not are exactly the `0x16` block, which the index never rows for.

## Bink2 video (`.bk2`)

```
+0x00  'KB2'   magic            +0x14  u32  width
+0x03  u8      version letter   +0x18  u32  height
+0x04  u32     payload size     +0x1c  u32  frames per second
+0x08  u32     frame count      ...
+0x10  u32     frame count, again
```

A container occupies `align(0x800, payload size)`; validated against the distance to the
next container. The duplicate frame count is the field that gave a false lead in
`restofworld` before the `KB2` magic was found.

| archive | movies | covered | share |
| --- | ---: | ---: | ---: |
| `movies.rpf` | 515 | 8,831,840,256 B | 99.993 % |
| `core_restofworld.rpf` | 11 | 1,241,526,272 B | 95.814 % |
| `story000_restofworld.rpf` | 7 | 120,193,024 B | 60.595 % |
| `story000.rpf` | 264 | 3,327,913,984 B | 16.621 % |

Tool: `tools/bink_index.py`. Validation is the width/height/fps triple — random `KB2`
bytes inside video data reject. Status: **exact** for the size rule, **measured** for the
rejection filter.

## Audio (`ADAT` / AWC)

Header: `ADAT`, `u16` version, `u16` flags, `u32` stream count, `u32` header size —
where the header size doubles as the data offset.

The stream table holds words `id:29 | tag_count:3`; the count is in the **high**
three bits. The chunk table's *position* depends on the variant, but its *shape* does
not: four records per stream (`0x36 0x55 0x76 0xa3`) and it ends **exactly at the
header size**.

| variant | chunk table starts at | status |
| --- | --- | --- |
| `0xff21` | fixed `0x50` | exact |
| `0xff02` | `0x10 + 4·count` | exact |
| `0xff61` | longest valid 8-byte suffix before the header size | measured |
| `0xff25` | same suffix scan | measured |

Record: `type:8 | size:28 | offset:28`. A bank ends at its furthest record, rounded up
to `0x800`. In `audio.rpf` these rules classify **99.687 %** of 28.5 GB as 7,159
banks; the residual is the archive front region plus bytes that merely spell `ADAT`.

Streams decoded: 93,344 Opus + 1,818 XMA2 + 73 ACE1, zero failures.
Status: **exact** for `0xff21`/`0xff02`; **measured** for the suffix-scanned variants.

---

## Verify

```sh
bash tools/check.sh                                   # 26 analysis checks
uv run python tools/script_meta.py script.rpf --index output/index/script.tsv --dump 1
uv run python tools/script_sections.py --out handoff/script-sections.tsv
uv run python tools/pe_scan.py sections
```
