# The fourteen Opus export exceptions

2026-11-21. Only the fourteen failed rows in
`handoff/audio-opus-decode.tsv` were opened. All fourteen independently
parse as length-prefixed Opus and decode at 48 kHz.

| Cases | Verified rule |
| --- | --- |
| 10 descriptors at 12 kHz and one at 28 kHz | Decode packets at 48 kHz. Every seek boundary and last-packet start matches the 48 kHz counts. For a nominal-rate copy, resample the PCM with `ffmpeg -i INPUT.wav -ar RATE OUTPUT.wav`. Do not substitute a smaller rate in the WAV header. In the 28 kHz case, 86,400 decoded frames become 50,400 at 28 kHz. |
| `00000001126d9000.awc` stream 2 | Valid sequential Opus, 31 packets and 29,760 decoded frames. The physical block boundary is 24,960 and the last packet starts at 28,800. The seek table says 24,000 and 30,720. Export untrimmed PCM and flag the inconsistent seek table. |
| `000000027dcd2000.awc` stream 0 | Valid sequential Opus, 53 packets and 50,880 decoded frames. No 0xA3 seek chunk is present for the stream. Export untrimmed PCM with seek unavailable. |
| `00000002f5c82000.awc` stream 0 | Valid stereo silence. Sixty-two identical 3-byte packets `fc ff fe` decode to 59,520 zero frames. The scalar seek endpoint is 117,120, exactly twice the last packet's start. Preserve the encoded silence. |

The two seek exceptions validate packet extents and decoder output.
Runtime seeking and exact trim for those streams remain unverified.
All WAV exports are untrimmed. The 11 rate-converted copies are
optional derivatives.

```sh
mkdir -p output/extracted/audio-opus-exceptions
python3 -B tools/data_opus_exceptions.py --output output/extracted/audio-opus-exceptions --resample > output/extracted/audio-opus-exceptions/manifest.tsv
```

Input rows come from the existing manifest. The resulting report records
AWC-relative payload offsets, channel counts, declared counts, packet sizes,
physical block boundaries, seek entries, and silence checks.
