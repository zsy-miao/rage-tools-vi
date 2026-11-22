# Audio (`audio.rpf`)

`audio.rpf` contains **6,625 `ADAT` AWC containers / 23.51 GB**. The GTA VI
container is a new layout, not the GTA V AWC format parsed by vgmstream.

## Container variants

Three flag families are known, and the payload layout differs between them:

| Flags | `data_offset` | Per-stream header | Chunk table | Status |
| --- | --- | ---: | --- | --- |
| `0xff21` | `20 + 42·n` | 42 B | at `0x50`, 8-byte records | decoded |
| `0xff02` | `16 + 60·n` | 60 B | at `0x10 + 4·n` | **decoded** |
| `0xff25` | compact | — | ends at `data_offset` | open |
| `0xff61` | — | — | — | decoded (rare) |

A chunk record is a little-endian `u64` packing `offset:28 | size:28 | type:8`,
so the type byte is the record's high byte. `0xff02` streams own exactly seven
chunks, in order `0x36 0x55 0x5c 0x76 0xa3 0xb2 0xbd`.

| Field | `0xff21` | `0xff02` |
| --- | --- | --- |
| stream index at `+0x10` | `u16[n]`, monotonic | none; `4·n` bytes of per-stream data |
| `data_offset` (6 streams) | `0x110` | `0x82` |
| `0x76` rate | low `u16` at `+0x08` (`0xBB80` = 48 kHz) | same |

The `0x76` descriptor is 32 bytes: sample count at `+0x00`/`+0x0c`, rate as the
low `u16` at `+0x08`, codec at `+0x1c`, codec sub-ID at `+0x1d`. Reading the rate
as a `u32` yields nonsense on both variants.

## The per-stream word

The field that decides how many chunks a stream owns is a single `u32`, and its two
halves do different jobs:

```
 31              3 2   0
+-----------------+-----+
|   stream id     | tags|
+-----------------+-----+
  29 bits           3 bits
```

The tag count sits in the **high three bits**, not the low ones. Reading it as a
plain integer gives a stream id in the millions for ordinary streams, which is what
made the first parser look broken; masking the top three bits yields sensible ids,
and masking the bottom three yields chunk counts that match the chunk table exactly.

This is also why the chunk-table search had to be a suffix scan: the table is
located relative to `data_offset`, and `data_offset` depends on the tag count, so
the two have to be solved together (`tools/awc_chunk_table.py`).

!!! note "Verification state"
    The bit split above is stated in the upstream layout notes and is consistent
    with every stream decoded so far (93,344 Opus, 1,818 XMA2, 73 ACE1,
    zero failures), but it has not been re-derived as a standalone measurement
    since the extraction volume went offline. Treat it as inherited-but-consistent
    rather than freshly counted.

## `story000` cutscene audio

`story000`'s 9.56 GB unclassified span is a second audio archive: 63,853 AWC
containers, 98.4 % `0xff02`, all codec `0x0b` (Opus) at 48 kHz. A whole-file scan
with the rules above indexes **63,325 banks / 9,212,590,080 B = 46.011 %** of that
20 GB archive, and raises its classified share from **35.39 % to 81.40 %**
(`output/index/story000-adat.tsv`). Decoding it
produced **196,350 streams / 148.3 hours / 47.7 GB of WAV** in
`output/extracted/story000-opus/`. Opus packets are framed `[u16 size][packet]`
inside `0x800`-byte blocks, the same as `audio.rpf`.

Tools: `tools/awc_framing_ff02.py` (variant census) and
`tools/extract_awc_ff02.py` (WAV export with manifest and SHA-256).

The `0x76` descriptor is 32 bytes: sample count at `+0x00`/`+0x0c`, sample rate
at `+0x08`, codec at `+0x1c`, and codec sub-ID at `+0x1d`.

## Index coverage

The original stream index classified **99.93 % of `audio.rpf` as `unclassified`** —
it recognises compressions, and an AWC bank is neither compressed nor opaque. That
was an *index* gap, not missing data, and it is now closed:

| source | banks | bytes |
| --- | ---: | ---: |
| extraction manifest (`0xff21` pass) | 6,625 | 23,510,392,992 |
| gaps between them (`0xff21`, `0xff02`, `0xff61`) | 534 | 4,943,599,616 |
| **total** | **7,159** | **28,453,992,608 = 99.687 %** |

Both variants share one rule: the chunk table holds four records per stream and ends
exactly at `header_size`, with `type:8 | size:28 | offset:28` per record. Only the
table's start differs — `0x50` for `0xff21`, `0x10 + 4·count` for `0xff02`. A bank
ends where its furthest record ends, rounded up to `0x800`.

Three rules finish the job, applied in this order:

1. a computable table position (`0xff21` at `0x50`, `0xff02` at `0x10 + 4·count`),
   with records-per-stream derived from `header_size` rather than assumed;
2. a suffix scan — the longest valid 8-byte record run ending at `header_size` — for
   `0xff25`/`0xff61`, which carry no computable position;
3. the same suffix scan as a fallback when the computable rule does not close, which
   catches banks carrying an extra per-stream table (one bank needed exactly this).

Scan alignment is 4 bytes, not `0x800`: most banks are `0x800`-aligned but a handful
sit on a 4-byte boundary. Validation is what keeps the looser scan honest.

The residual **0.313 % (89,462,064 B, 275 gaps)** is accounted for: **19,509,248 B**
is the archive's own front region, and the other **69,952,816 B** are regions where
`ADAT` bytes exist but no candidate validates at any offset shift — the bytes are not
a container header there.

A magic scan alone does not validate: `ADAT` occurs at 7,159 aligned
offsets in `audio.rpf`, and **none** validate against `awc_parse.py`'s tag model,
because that model is the Leonida/story000 layout rather than the `0xff21`/`0xff02`
one. Validating one layout with the other yields confident garbage — which is exactly
what the first 7,159 rejections were.

## How much audio there is

Reading each container's chunk table, without decoding anything
(`tools/extract_adat_gaps.py` + `tools/audio_census_totals.py`):

| archive | containers | streams | stream data |
| --- | ---: | ---: | ---: |
| `audio.rpf` | 7,159 | 1,606,237 | 22.47 GB |
| `story000.rpf` | 63,325 | 213,579 | 6.06 GB |
| **total** | **70,484** | **1,819,816** | **28.53 GB** |

| codec | in the corpus | decoded | share |
| --- | ---: | ---: | ---: |
| opus | 1,795,416 | 93,344 | 5.2 % |
| xma2 | 1,818 | 1,818 | **100 %** |
| ace1 | 227 | 73 | 32 % |

The XMA2 number is the control: 1,818 obtained by decoding and 1,818 from the chunk
tables, by independent paths. So the tables are read correctly, and the Opus figure
means the decode passes covered about a twentieth of the streams that exist.

Container flags in `audio.rpf`: `0xff25` 3,008, `0xff02` 2,071, `0xff21` 1,270 — the
compact variant dominates, which is why the first extraction pass (a `0xff21` scan)
under-counted the archive so badly.

## Decoding a previously missed container

The old probe looked for the data offset at `+0x0c` — the `0xff21` layout — so it found
nothing in the `0xff02` pools. `tools/decode_adat_stream.py` uses the verified table
rules instead, and the first stream from an untouched container decodes:

```
audio.rpf+0x16437000  (0xff02, 1,914 streams)
stream 0: Opus, mono, declared 32,000 Hz, 116,480 samples
          4,096 B payload -> 124 packets -> 119,040 samples = 2.48 s
          peak 0.743 FS, RMS 0.107 FS — not silence
```

Two details worth knowing before decoding at scale:

- the `0x76` rate is the **source** rate (32 kHz here, 48 kHz in the packs measured
  earlier); libopus only produces 48 kHz and rejects other rates with `OPUS_BAD_ARG`,
  so always decode at 48 kHz;
- the decoded length is ~2 % longer than the declared sample count, because the
  declared value is post-trim.

## Decode coverage by variant

A sample of 24 evenly spaced containers, 8 streams each (`tools/decode_adat_sample.py`):

| variant | containers | streams decoded | audio |
| --- | ---: | ---: | ---: |
| `0xff02` | 9 | 72 | 3.0 min |
| `0xff21` | 5 | 32 | 2.7 min |
| `0xff61` | 1 | 8 | 0.1 min |
| `0xff25` | 9 | **0** | — |

112 streams, 5.8 minutes, median RMS 0.13 FS, 2 near-silent. `0xff61` decodes once its
table is found by suffix scan.

**`0xff25` has no chunk table at all.** A sampled container reports `count = 2`,
`header_size = 64`, and inside the header there is an inline descriptor ending
`07 00 | 80 bb | 0b | 01 | ff ff` — flags, `0xbb80` (48 000 Hz), codec, channels,
terminator. Over 600 such containers, **95.3 %** are Opus (codec `0x0b`) at 48 kHz with
one or two channels; stereo is the majority (401 stereo, 171 mono).

So the compact variant describes its streams in place rather than through records, which
is why the table model found nothing.

Two further probes narrowed it without solving it: only **32 of 200** containers admit a
valid 8-byte table under any byte shift (two records per stream where they do), and no
field in the first 64 bytes scales with the container size. The type-like bytes sit at
*odd* offsets (`0x23`, `0x2b`, `0x2f`, `0x3f`), so the alignment is not the one the other
variants use.

Further tests, all negative except one identification: no block framing at sizes
`0x100`–`0x2000` and shifts 0–3; packet chains stop after 12–25 packets; and the repeated
payload offset `+0x860` holds the `a0 00 f8` **marker** already documented in
`tools/awc_framing.py`, not packet data. Big-endian `u16` and little-endian `u32` length
prefixes both fail there too.

**Solved.** A `0xff25` container is a sequence of `0x800`-byte blocks, each carrying its
packets from `block + 0x60`; runs are a fixed size at a fixed period, verified across nine
containers. Decoding packet by packet gives, from one 266 KB container:

```
3,049 packets -> 60.98 s stereo   RMS 0.176   spectral flatness 0.0045
```

The variant that contributed nothing to every earlier pass accounts for roughly **50 hours**
of audio across its 3,008 containers in `audio.rpf`. Decode with
`tools/decode_adat_stream.py --ff25`.

Earlier measurements that bounded the problem, retained because they explain why the
structural routes failed:

- the body entropy is 7.74–7.79 against 3.4–4.4 for the header, so the containers do hold
  audio;
- **`header_size` is not the data start** — one container with `header_size = 64` has the
  `… 80 bb 0b 01 ff ff` descriptor sitting *at* offset 64, so the descriptor block extends
  past it;
- the payload is packet-framed but not block-framed: scanning a whole container finds
  1,678 short runs of ≥12 valid size-prefixed packets, while all 130 `0x800`-aligned
  blocks fail the other variants' block rule;
- a table-like run in the header is an arithmetic sequence of step 90 read one byte in,
  the third independent sign that this variant's fields sit at odd offsets.

What is not yet located is the **payload start and the split between streams**; until
both exist, no `0xff25` stream is decoded, and the census keeps its 3,008 containers'
streams out of the decoded totals.

## Codec status

The corpus scan found 2,320 parsed streams:

| Codec | Streams | Status |
| --- | ---: | --- |
| `0x0b` | 2,081 | **Opus; decoded** |
| `0x05` | 166 | **XMA2; decoded** |
| `0x02` | 73 | **ACE1 impulse responses; decoded** |

### `0x05` = XMA2

The first wrapper used `wFormatTag=0x0161` (WMAudio2), so ffmpeg called the
wrong decoder. The correct XMA2 tag is **`0x0166`**. With it, **151 unique
streams decode to 86 MB of PCM WAV**; all 151 are non-silent and 148 have
spectral flatness below 0.1. The engine rumble in the decoded set is a
human-confirmed check. The 15 missing `0x05` rows are fragmented AWC entries.

### `0x0B` = Opus

Each `0x800`-byte `0x55` block is a sequence of

```text
[u16le packet size][size-byte Opus packet] ...
zero padding to the block end
```

The `a0 00 f8` prefix is a 160-byte packet (`f8` is its TOC); the next packet
starts at 162. libopus decodes the controls at 48 kHz, and every `0xA3` block
boundary matches cumulative decoded frames × channels.

Bulk export: **2,081/2,081 streams / 2.5 GB untrimmed WAV**, zero decode
failures. 11 non-48 kHz streams are decoded at 48 kHz with source rate
recorded; 5 seek flags and 1 encoded silence are preserved. Pre-skip and
end-trim are bounded by controls but not exactly determined.

### `0x02` = ACE1 impulse responses

Each `0x2000`-byte tile is 1,024 interleaved complex float32 bins of a
2,048-point real FFT, stored with the Nyquist bin omitted. Inverse-transform
the tiles, restore the missing alternating Nyquist component from the zero
leading half and adjacent overlaps, concatenate the second halves, and trim to
the tap count at `0x76 +0x0c`. The terminal `0x2000` bytes are an `ACE1`
trailer: `0xfffface1` + 15 LE `u16` pairs + zero padding.

`tools/extract_awc_ace1.py` exported **73/73 streams / 6 MB float32 WAV**; all
controls have overlap/padding RMS below `8e-9`. The first trailer pair values
are not needed for reconstruction and remain unassigned.

## Reproduce

```sh
# full audio.rpf output: AWC + framing + XMA2 + Opus
tools/rebuild_audio.sh SOURCE/audio.rpf output/extracted

# individual subsets from an existing AWC extraction
python3 tools/extract_awc_xma2.py --limit 0
python3 tools/extract_awc_opus.py --limit 0
python3 tools/extract_awc_ace1.py --limit 0
```

Artifacts: `handoff/audio-awc.md`, `handoff/audio-awc-decode.md`,
`handoff/data-awc-opus.md`, `handoff/data-awc-trim-ace1.md`,
`handoff/audio-awc-framing.tsv`, `handoff/audio-xma2-decode.tsv`,
`handoff/audio-opus-decode.tsv`, `handoff/audio-ace1-decode.tsv`.
