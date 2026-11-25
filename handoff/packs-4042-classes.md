# u16_4042 size-class behavior

Top classes split into two regimes:

| Size | Streams | Entropy | Zero frac. | Adjacent equal | Regime |
| ---: | ---: | ---: | ---: | ---: | --- |
| 1,040 | 2,535 | 2.80 | 0.574 | 0.503 | metadata |
| 393,216 | 2,291 | 7.98 | 0.004 | 0.005 | compressed/high-entropy |
| 131,072 | 2,155 | 6.21 | 0.296 | 0.247 | structured |
| 851,968 | 1,513 | 7.98 | 0.003 | 0.005 | compressed/high-entropy |
| 256 | 1,450 | 2.97 | 0.629 | 0.545 | metadata |
| 196,608 | 1,009 | 6.05 | 0.309 | 0.254 | structured |
| 262,144 | 930 | 5.15 | 0.443 | 0.360 | structured |
| 25,424 | 919 | 4.25 | 0.437 | 0.490 | metadata/structured |
| 327,680 | 870 | 7.52 | 0.119 | 0.095 | mixed |
| 65,536 | 730 | 5.23 | 0.323 | 0.397 | structured |

The high-entropy classes (393,216; 851,968; 524,288) look compressed or packed;
the mid-entropy classes (131,072; 196,608; 262,144; 65,536) look structured.
The 1,040/256 classes are metadata-like.

This is consistent with a resource family containing both metadata and
compressed/structured payloads, but it does not yet distinguish texture, audio,
or geometry.

Artifact: `handoff/packs-4042-classes.tsv`; tool:
`tools/probe_4042_classes.py`.
