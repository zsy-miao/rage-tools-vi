# AWC trim and 0x02 control results

2026-11-21. The follow-up uses six mono streams and one stereo WAV
from the Opus controls, plus six streams from each of two 0x02 containers.
It uses no new corpus scan.

## 0x0B Opus

Let `C` be the decoded channel count, `T` the number of decoded frames
per channel, and `N` the little-endian count at format `0x76 +0x00`.
In the controls, `0xA3` entries use interleaved sample units. The desired
header count is consistent with `L = N / C` frames. The stereo control
rules out `N` frames per channel because `N > T` and validates the
channel multiplier independently at each storage-block boundary.

To make an exactly aligned export after independent proof of an initial
skip `P`, retain frames `[P, P + L)` and remove `T - L - P` from the end.
The metadata seen here bounds `P` to `0..T-L`; it does not determine
the split. The mono stream 0 gives `63360 - 60741 = 2619` total trim
frames. Stereo stream 0 gives `267840 - 531646/2 = 2017`. Leading exact
zeros vary from 26 to 265 in the measured WAVs, trailing zeros vary from
0 to 1903, and all first 20 ms windows contain nonzero signal. Trimming
those zeros, two whole packets, or a standard Opus lookahead would need
additional evidence. The seek table's last entry is the last packet
start and supplies no exact end trim. Keep the bulk export untrimmed
and record the declared units, channels, and decoded frames.
[Opus encoder API on stream-specific lookahead](https://www.opus-codec.org/docs/opus_api-1.6/group__opus__encoderctls.html).

For bulk export, the existing driver calls `load_opus()`, `streams()`,
and `decode_stream()` from `tools/data_awc_opus_probe.py`. The bounded
entry point is:

```sh
python3 -B tools/data_awc_opus_probe.py output/extracted/audio-awc/01/000000000129b000.awc --output output/extracted/audio-opus/000000000129b000
```

## 0x02 float32 and ACE1 structure

All 12 controls satisfy `len(0x55) = 4 × N` using the `0x76 +0x00`
count. The terminal `0x2000` bytes start with little-endian
`0xfffface1`, followed by fifteen `(u16le, u16le)` pairs at
`+0x04..+0x40` and then all-zero padding. The second value in every
pair is nondecreasing. The last pair's second value predicts
`(len(0x55) - 0x2000) / 0x2000` exactly. The prefix consists of
that many `0x2000`-byte blocks of finite little-endian float32 words.
For example, `0x800..0x26800` contains 19 blocks, and its ACE1 trailer
ends at AWC-relative `0x28800`.

The structure supports a native split at `offset + 4 × N - 0x2000`.
The first values in the trailer pairs and the signal representation
remain unknown. Adjacently paired float words do not form full
conjugate-symmetric 1024-bin spectra per block, and `0x76 +0x0c` does
not repeat `N` on this codec. Treat the prefix as float data and keep
the trailer. A playable PCM format assignment needs more evidence.

```sh
python3 -B tools/data_awc_trim_controls.py output/extracted/audio-awc/01/000000000129b000.awc --opus-wavs output/extracted/audio-opus/000000000129b000
python3 -B tools/data_awc_trim_controls.py output/extracted/audio-awc/697/0000000697c43000.awc --ace1 --output output/extracted/audio-ace1/0000000697c43000
python3 -B tools/data_awc_trim_controls.py output/extracted/audio-awc/697/0000000697d6c000.awc --ace1
```
