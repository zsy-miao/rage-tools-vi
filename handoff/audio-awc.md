# audio.rpf AWC extraction report

Source: Xbox build `GTA6.Xbox.v1.0.2.1-CYBERLEEK`.
Scope: raw AWC containers, container/framing analysis, and decode experiments.

## Result

- AWC magic `ADAT` at `0x129b000` inside `audio.rpf`.
- Extracted **6,625 containers**, **23,510,392,992 bytes** (22 GB).
- Manifest: `manifest.tsv` with start/end, flags, streams, data_offset, SHA-256.
- Header: version 1, flags `0xff21`, 6–24 streams, `data_offset` consistent.
- Chunk types observed: `0x55` data, `0x36` peak, `0xA3` seektable,
  `0x76` new format/stream chunk.
- `0x76` carries sample rate, sample counts, codec ID, and a codec sub-ID.
- Data chunk sizes are multiples of **2048** bytes.

## Framing scan

`tools/awc_framing.py --limit 0` parsed **2,320 stream rows** from the 6,625
containers into `handoff/audio-awc-framing.tsv`.

- Codecs: `0x0b` 2,081; `0x05` 166; `0x02` 73.
- Rates: 48,000 (2,143), 32,000 (165), 12,000 (10), 28,000 (1), 32,016 (1).
- Codec sub-IDs: `0x01` 2,025; `0x02` 295.
- `0x76` is a 32-byte descriptor: sample count at `+0x00`/`+0x0c`, rate at
  `+0x08`, codec at `+0x1c`, sub-ID at `+0x1d`.
- Many 2,048-byte data chunks start with `a0 00 f8` and repeat the same three
  bytes at **offset 162** (1,451 rows). This is the Opus length prefix: `a0 00`
  is a 160-byte packet and `f8` is the first TOC byte; 162 = 2 + 160.

## Decode attempts

- **Codec `0x05` = XMA2: solved.** The first wrapper used `wFormatTag=0x0161`
  (WMAudio2), so ffmpeg called the WMA decoder and produced silence/noise. The
  correct XMA2 tag is `0x0166`. `tools/extract_awc_xma2.py` decoded **151 unique
  streams to 86 MB of WAV** (166 rows selected; 15 fragmented entries missing);
  all 151 are non-silent and 148 have flatness < 0.1. This is the first
  non-zlib codec family decoded from `audio.rpf`.
- `vgmstream` AWC parser: rejects the GTA VI `ADAT` header (expects GTA V AWC).
- Synthetic UEBA/Bink Audio wrapper (`ABEU` + `9999` packet headers):
  - vgmstream accepts it and reports `RAD Game tools Bink Audio`;
  - whole chunk decodes as a short burst only; 2,048/1,024/512 splits are silence;
  - offset sweep produced three one-burst candidates, no continuous audio.
- **Codec `0x0B` = Opus: solved.** Each `0x800`-byte `0x55` block is a sequence
  of `[u16le size][size-byte Opus packet]`, zero-padded. libopus decodes the
  tested mono and stereo controls directly, and every `0xA3` block boundary
  matches cumulative frames × channels. `tools/extract_awc_opus.py` exported
  **2,081/2,081 streams / 2.5 GB untrimmed WAV**, zero decode failures.
  11 non-48 kHz streams are decoded at 48 kHz with source rate recorded;
  5 seek flags and 1 encoded silence are preserved. Pre-skip/end-trim remain
  open; keep the bulk untrimmed.
- **Codec `0x02` = ACE1 impulse responses: decoded.** Each `0x2000`-byte
  prefix tile is 1,024 complex float32 bins of a 2,048-point real FFT with the
  Nyquist bin omitted. Inverse-transform, restore the missing alternating
  component, concatenate second halves, trim to the `0x76 +0x0c` tap count.
  The terminal `0x2000` bytes are an `ACE1` trailer (`0xfffface1` + 15 LE u16
  pairs + zero pad). `tools/extract_awc_ace1.py` exported **73/73 streams /
  6 MB float32 WAV**; overlap/padding RMS < 8e-9 on controls.
- The old UEBA/Bink path was a wrong-decoder artifact: vgmstream accepted the
  synthetic wrapper but received Opus packets.

## Interpretation

The container is clear. **`0x05` is XMA2**, **`0x0B` is Opus**, and **`0x02`
is ACE1 float32 impulse responses**; all three decode. No AWC/XXTEA encryption
was found in the tested payloads.

The remaining audio work is exact Opus pre-skip/end-trim, the 14 exceptional
Opus streams, and the unassigned first ACE1 trailer pair values.

Full experiment log: `handoff/audio-awc-decode.md`.

## Artifacts

- `output/extracted/audio-awc/` — 6,625 `.awc` + `manifest.tsv`
- `handoff/audio-awc-framing.tsv` — per-stream codec/rate/size/marker table
- `handoff/audio-xma2-decode.tsv` — 166 codec-`0x05` rows with decode status/SHA
- `handoff/audio-opus-decode.tsv` — 2,081 codec-`0x0B` rows with decode status/SHA
- `handoff/audio-ace1-decode.tsv` — 73 codec-`0x02` impulse-response rows with SHA
- `handoff/data-awc-ace1-ir.md` — ACE1 inverse-FFT/reconstruction contract
- `handoff/data-awc-opus.md` — bounded Opus framing/seek verification
- `handoff/data-awc-trim-ace1.md` — trim bounds and `0x02` ACE1 controls
- `handoff/audio-awc-decode.md` — detailed decode experiments
- `tools/extract_awc.py` — ADAT scanner/extractor
- `tools/awc_framing.py` — header/chunk/marker inventory
- `tools/bruteforce_ueba.py` — Bink Audio packet sweep
- `tools/test_awc_xma2.py` — XMA2 wrapper sweep
- `tools/extract_awc_xma2.py` — codec-`0x05` XMA2 decode/extract
- `tools/extract_awc_opus.py` — codec-`0x0B` Opus bulk export
- `tools/extract_awc_ace1.py` — codec-`0x02` ACE1 impulse-response export
- `output/extracted/audio-xma2/` — 151 decoded WAVs + manifest (local-only)
- `output/extracted/audio-opus/` — 2,081 decoded WAVs / 2.5 GB + manifest (local-only)
- `output/extracted/audio-ace1/` — 73 float32 impulse responses / 6 MB + manifest
- `output/audio-awc-verification.tsv` — not yet generated
