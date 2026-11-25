# AWC codec 0x0B bounded verification

2026-11-21. This probe used three local ADAT files and did not rescan the
archive corpus.

## Verified codec and framing

- Codec `0x0B` is **Opus** in the eight tested streams. Sub-ID `0x01`
  is mono in six controls and sub-ID `0x02` is stereo in two holdouts.
  The packet TOC confirms the actual channel count.
- Divide the `0x55` chunk into `0x800`-byte storage blocks. Each starts
  with `[u16le packet_bytes][packet_bytes of Opus]`. The next length
  field is at `current + 2 + packet_bytes`. The remaining all-zero bytes
  pad a block. Start again at the next `0x800` boundary.
- In the mono control, `a0 00 f8` means a 160-byte Opus packet starting
  with TOC `0xf8`. That TOC denotes one 20 ms mono fullband CELT frame.
  The second such header starts 162 bytes later. Subsequent packet
  sizes and TOCs vary. Stereo controls start with `0xfc` and have first
  lengths of 240 and 320 bytes.
- Decode consecutive packets with one 48 kHz libopus decoder per stream.
  At every storage-block start, cumulative decoded frames multiplied
  by the channel count match the little-endian `u32` entries in chunk
  `0xA3`. In the eight tested streams its terminal entry gives the
  last Opus packet's start, in the same units.
- The synthetic Bink wrapper passed a container check and fed Opus to
  the wrong decoder. Its transient is not evidence for a Bink payload.
  The tested 0x0B data decodes directly. The probe exports untrimmed PCM
  because the exact encoder pre-skip and end-trim rules remain open.

Mono stream 0 at AWC-relative `0x4a80..0x6280` decodes 66 packets.
Block starts are 0, 23,040, and 48,000 sample frames. The last packet
starts at 62,400 and total decoded length is 63,360 frames. The stream
descriptor declares 60,741 samples.

## Optional 0x02 control

The existing framing table records four payload bytes per declared
sample in all 73 rows tagged `0x02`. In the six streams of one
control, interpreting the payload as little-endian floats produces one
nonfinite word, `0xfffface1`, at `declared_count - 2048` and finite values
elsewhere. Signal peaks exceed one. This is evidence for float32 data
with an embedded structured region. A complete PCM or impulse-response
format assignment remains open.

## Run from the repository root

```sh
python3 -B tools/data_awc_opus_probe.py output/extracted/audio-awc/01/000000000129b000.awc --output output/extracted/audio-opus/000000000129b000
python3 -B tools/data_awc_opus_probe.py output/extracted/audio-awc/02/0000000002db1000.awc --output output/extracted/audio-opus/0000000002db1000
python3 -B tools/data_awc_opus_probe.py output/extracted/audio-awc/03/0000000003dc5000.awc
python3 -B tools/data_awc_opus_probe.py output/extracted/audio-awc/697/0000000697c43000.awc --float-control
```

Protocol references: [RFC 6716 §3.1](https://www.rfc-editor.org/rfc/rfc6716.html#section-3.1)
and [libopus decoder API](https://www.opus-codec.org/docs/opus_api-1.6/group__opus__decoder.html).
