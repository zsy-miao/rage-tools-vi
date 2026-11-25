# GTA VI AWC/ADAT decode notes (2026-11-21)

Source: Xbox build `GTA6.Xbox.v1.0.2.1-CYBERLEEK`.
Scope: codec/framing experiments on the extracted `audio-awc` containers.
Status: **container parsed; `0x05`=XMA2, `0x0B`=Opus, `0x02`=ACE1 decoded**.

## New container layout

The GTA VI `ADAT` header is not the GTA V AWC layout used by vgmstream.

| Offset | Field |
| --- | --- |
| `0x00` | `ADAT` magic |
| `0x04` | `u16` version = 1 |
| `0x06` | `u16` flags = `0xff21` (all sampled containers) |
| `0x08` | `u16` stream count |
| `0x0c` | `u32` data offset |
| `0x10` | `u16[streams]` stream chunk indexes |
| `0x50` | start of `u64` chunk table; entries end at `data_offset` |

Chunk entry packing remains the earlier `type:8 | size:28 | offset:28` layout.
Chunks observed: `0x55` data, `0x36` peak, `0xA3` seek table, `0x76` format.

## `0x76` format descriptor (32 bytes)

Example (`000000000129b000.awc`, stream 0):

```
45 ed 00 00 ff ff ff ff 80 bb 50 01 45 ed 00 00
00 00 00 00 00 00 00 00 ff ff ff ff 41 34 0b 01
```

| Offset | Interpretation |
| --- | --- |
| `+0x00` | `u32` sample count |
| `+0x04` | `0xffffffff` |
| `+0x08` | `u16` sample rate (48000, 32000, 12000, ...) |
| `+0x0a` | `u16` unknown, likely peak/headroom or block metric (`0x01fc`) |
| `+0x0c` | `u32` sample count again |
| `+0x10` | zero |
| `+0x14` | zero |
| `+0x18` | `0xffffffff` |
| `+0x1c` | `u8` codec ID |
| `+0x1d` | `u8` codec sub-ID (`0x01` or `0x02` observed) |
| `+0x1e` | `u16` zero in all sampled rows |

## Corpus scan

`tools/awc_framing.py --limit 0` parsed **2,320 parsed stream rows / 6,625 containers**
into `handoff/audio-awc-framing.tsv`.

- Codec IDs: **`0x0b` 2,081**, **`0x05` 166**, **`0x02` 73**.
- Rates: 48,000 (2,143), 32,000 (165), 12,000 (10), 28,000 (1), 32,016 (1).
- Codec sub-IDs: `0x01` 2,025, `0x02` 295.
- Data-chunk sizes are multiples of 2,048 bytes; sizes range from 2,048 to
  9,680,896 bytes.
- The 2,048-byte data chunks often begin with **`a0 00 f8`** and repeat the same
  three bytes at **offset 162** (1,451 rows). Six large streams repeat the gap
  pattern `162,...,162,266,162,...` up to the 16-marker scan limit. 840 rows
  have no marker in the first 16 hits, 23 have one, and 6 hit the 16-marker cap.

The marker is the Opus length prefix: `a0 00` = 160-byte packet, `f8` = first
TOC byte, so the next packet starts at 162. It is not a Bink or XMA2 marker.

## Decode attempts

### 1. vgmstream AWC

`vgmstream` rejects the GTA VI `ADAT` header because it expects the GTA V AWC
layout. This is a container mismatch, not yet a codec verdict.

### 2. XMA2 WAV — solved for codec `0x05`

The first wrapper used `wFormatTag=0x0161`, which is **WMAudio2**, so ffmpeg
called the WMA decoder and produced silence/noise. The correct XMA2 tag is
`0x0166`. `tools/test_awc_xma2.py` now writes `XMA2WAVEFORMATEX` with
`wFormatTag=0x0166`, `BytesPerBlock=2048`, and `BlockCount` from the `0x55`
size; `tools/extract_awc_xma2.py` selects streams from the framing TSV and
decodes them to PCM WAV.

Result on the corpus: **166 codec-`0x05` rows selected; 151 unique streams
decoded to WAV (86 MB); all 151 are non-silent and 148 have flatness < 0.1**.
The 15 missing rows are fragmented/misparsed AWC entries, not decoder failures.
The first sample `000000069dbc6000` decodes to 5.5 s at 32 kHz with
RMS 0.234, flatness 0.038, harmonic 0.398; its spectrogram is continuous with
low-frequency harmonic structure, not a decoder transient.

This is the first non-zlib codec family decoded from `audio.rpf`.

### 3. Synthetic UEBA/Bink Audio wrapper (wrong decoder)

`tools/bruteforce_ueba.py` writes an `ABEU` header (UEBA v1), wraps each AWC
payload as `[0x9999][u16 packet_size][payload]`, and feeds vgmstream. vgmstream
accepts the synthetic container and reports `RAD Game tools Bink Audio`.

- Whole `0x55` chunk as one packet: one short burst (~90 ms), then zeros.
- Splitting at 2,048/1,024/512 bytes: silence.
- Offset sweep 0..256 over 20 chunks (5,140 candidates): three non-silent
  candidates, all short bursts; best flatness 0.189 / harmonic 0.619 was a
  single transient, not continuous speech or music.

This was a wrong-decoder path: the synthetic wrapper passed Opus packets to a
Bink decoder. It is not evidence for a Bink payload.

### 4. Codec `0x0B` = Opus (solved)

Each `0x800`-byte `0x55` block is a sequence of
`[u16le packet size][size-byte Opus packet]`, zero-padded at the block end.
libopus decodes the controls at 48 kHz; every `0xA3` block boundary matches
cumulative decoded frames × channels. `tools/data_awc_opus_probe.py` verifies
the controls; `tools/extract_awc_opus.py` performs the bulk export.

Bulk result: **2,081/2,081 streams / 2.5 GB untrimmed WAV**, zero decode
failures. 11 non-48 kHz streams are decoded at 48 kHz with source rate
recorded; 5 seek flags and 1 encoded silence are preserved. Pre-skip/end-trim
is only bounded by the controls; the export stays untrimmed and records
declared units, channels, and decoded frames.

## Current interpretation

1. The container and `0x76` metadata are understood well enough to index every
   stream and compare codecs.
2. **Codec `0x05` is XMA2 in this build.** Direct XMA2 decoding produces
   continuous tonal audio, so this is no longer a hypothesis.
3. **`0x0B` is Opus**, not Bink. The synthetic UEBA path was feeding Opus to
   the wrong decoder.
4. **`0x02` is ACE1 float32 impulse responses.** Each `0x2000` tile is half of
   a 2,048-point real FFT; inverse-transform, restore the omitted Nyquist
   component, concatenate overlaps, and trim to `0x76 +0x0c`. The terminal
   `0x2000` bytes are an `ACE1` trailer. See `handoff/data-awc-ace1-ir.md`.
5. Remaining audio work: exact Opus pre-skip/end-trim, 14 exceptional Opus
   streams, and unassigned first ACE1 trailer pairs; no encryption was found in
   tested payloads.

### 5. Codec `0x02` = ACE1 impulse responses

`tools/data_awc_ace1_ir.py` reconstructs the float32 prefix with an inverse
real FFT and writes float32 WAV. `tools/extract_awc_ace1.py` exported **73/73
streams / 6 MB**; overlap/padding RMS is below `8e-9` on all controls. The
first trailer pair values are not needed for reconstruction.

## Reproduction

```bash
# container/stream inventory
python3 tools/awc_framing.py --limit 0

# synthetic Bink Audio sweep (needs numpy + vgmstream-cli)
/tmp/audio-venv/bin/python tools/bruteforce_ueba.py --workers 32 --max-offset 256

# XMA2 wrapper sweep (needs numpy + ffmpeg)
/tmp/audio-venv/bin/python tools/test_awc_xma2.py --limit 5

# decode every codec-0x05 stream to PCM WAV
/tmp/audio-venv/bin/python tools/extract_awc_xma2.py --limit 0

# decode every codec-0x0B stream to untrimmed PCM WAV
python3 tools/extract_awc_opus.py --limit 0

# decode every codec-0x02 ACE1 impulse response
python3 tools/extract_awc_ace1.py --limit 0
```

## Artifacts

- `handoff/audio-awc-framing.tsv` — per-stream codec/rate/size/marker table.
- `handoff/audio-xma2-decode.tsv` — 166 codec-`0x05` rows with decode status/SHA.
- `tools/awc_framing.py` — parser used to generate it.
- `tools/bruteforce_ueba.py` — synthetic UEBA packet sweep.
- `tools/test_awc_xma2.py` — XMA2 WAV wrapper sweep.
- `tools/extract_awc_xma2.py` — codec-`0x05` XMA2 decode/extract with manifest.
- `tools/extract_awc_opus.py` — codec-`0x0B` Opus bulk export with manifest.
- `tools/extract_awc_ace1.py` — codec-`0x02` ACE1 impulse-response export.
- `output/extracted/audio-xma2/` — 151 decoded WAVs + manifest (local-only).
- `output/extracted/audio-opus/` — 2,081 decoded WAVs + manifest (local-only).
- `output/extracted/audio-ace1/` — 73 float WAVs + manifest (local-only).
- `output/audio-tests/` — local-only WAV/spectrogram experiments (ignored).
