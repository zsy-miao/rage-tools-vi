# AWC 0x02 ACE1 impulse responses

2026-11-21. Verified on twelve streams from two local containers.

## Decode

1. Split `0x55` into the float32 prefix and the terminal `0x2000`-byte
   ACE1 trailer documented in [the layout controls](data-awc-trim-ace1.md).
   The little-endian `u32` at `0x76 +0x0c`, rather than `+0x00`, gives the
   number `L` of time-domain taps in the controls.
2. Each prefix tile is `0x2000` bytes. Read 1,024 interleaved complex
   float32 bins in little-endian order. This is the stored half of a
   2,048-point real transform, with the Nyquist bin omitted. There are
   `ceil(L / 1024) + 1` consecutive nonzero tiles. The later tiles are zero.
3. Inverse-transform each tile with a provisional zero Nyquist bin,
   normalizing by 2,048. The windows are 2,048 samples long and overlap by
   1,024. The first window's leading half is zero. The first half of each
   later window repeats the previous window's second half.
4. Restore the missing alternating component. For provisional windows
   `z[k]`, let `A(v) = mean((-1)^i * v[i])`. Set
   `a[0] = -A(z[0][0:1024])`, then
   `a[k+1] = a[k] + A(z[k][1024:] - z[k+1][:1024])`.
   Recover each window with `z[k][i] + a[k] * (-1)^i`.
5. Concatenate the second halves of the windows except the last, and
   keep the first `L` samples. Export as mono IEEE float32 WAV at the
   `0x76 +0x08` sample rate.

The final emitted lengths are 420, 31,400, and 117,991 taps across these
controls. After Nyquist restoration, both overlap disagreement and
out-of-range padding were below `8e-9` RMS on all twelve streams. For a
short control the entire second spectrum equals the first spectrum
multiplied by `(-1)^k`, independently confirming the half-window shift.
The tool does not yet assign semantics to the trailer's first pair
values. They are unnecessary for this reconstruction.

## Reproduction

```sh
python3 -B tools/data_awc_ace1_ir.py output/extracted/audio-awc/697/0000000697c43000.awc --output output/extracted/audio-ace1/0000000697c43000-ir
python3 -B tools/data_awc_ace1_ir.py output/extracted/audio-awc/697/0000000697d6c000.awc --output output/extracted/audio-ace1/0000000697d6c000-ir
ffprobe -v error -show_entries stream=codec_name,sample_rate,channels,duration_ts output/extracted/audio-ace1/0000000697d6c000-ir/stream-01.wav
```

The final command reports `pcm_f32le`, 48 kHz, one channel, and 117,991
sample frames. The output is an impulse response.
