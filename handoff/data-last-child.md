# Last child in data.rpf

Bus handoff #0151, 2026-11-21. Ranges are start-inclusive and end-exclusive.

The final child begins at archive offset `0x1a279000`. Under the observed
contiguous, disjoint trailer convention, its end is at or before archive offset
`0x1cab4000` (child-relative `0x283b000`). The exact end remains unresolved.

## Header and control

The child header's little-endian words at `+0x04`, `+0x08`, `+0x0c`, and
`+0x24` are `0x143c0`, `0x11300`, `0xf970`, and `1247`. They identify the
front boundaries, a 63,856-byte trailer, and the count. The root ends at
`0x1cb3c870`. Its trailer begins at `0x1cb37000`, calculated from the root's
`+0x0c = 0x5870`.

The reference child at `0x120d7000` has `+0x0c = 0x250` (592 bytes). Its
observed trailer candidate is `0x121d59b0..0x121d5c00` at archive scale and
`0xfe9b0..0xfec00` within the child. Thirteen zeros immediately precede it and
at least 32 zero bytes follow it. The control gives an observed boundary
pattern for comparison.

## Independently bounded PSIN

The likely-looking trailer immediately before the largest terminal gap is
`0x1cb1f9d0..0x1cb2f340` (child-relative `0x28a69d0..0x28b6340`). It lies
wholly inside the stored tail of a verified PSIN object:

| Part | Archive-relative | Child-relative |
| --- | --- | --- |
| PSIN stored extent | `0x1cab4000..0x1cb2f340` | `0x283b000..0x28b6340` |
| 34 wrapped zlib chunks and alignment | `0x1cab4000..0x1cb0d960` | `0x283b000..0x2894960` |
| Stored tail | `0x1cb0d960..0x1cb2f340` | `0x2894960..0x28b6340` |
| Terminal CHKS | `0x1cb2f32c..0x1cb2f340` | `0x28b632c..0x28b6340` |

All 34 wrapped streams independently verify their zlib checksums and inflate
to 64 KiB each. Their decoded bytes plus the `0x219e0` stored tail give
`0x2419e0` bytes. The PSIN sections parse to completion, and the CHKS length
field at `0x1cb2f334` is `00 24 19 e0`, matching the reconstructed size.
Decoded SHA-256 is
`a8fc9857c6a04d578a1ee61dad00502b1d281545dea7a4d98986e95331b389ae`.

An end between the PSIN start and end would split this object or place its
bytes in the trailer. There are only `0x7cc0` bytes from the end of the PSIN
to the root trailer, shorter than the child's declared `0xf970` trailer.
This rules out all ends after `0x1cab4000` under the contiguous, disjoint
trailer convention. The root-aligned candidate also overlaps four verified
zlib streams, three of which inflate to standalone PSIN objects.

## Endpoint blocker

The probe sampled `0x1caf7000..0x1cb37000`, used a zlib lookback at
`0x1ca0d960..0x1cb0d960` for the PSIN, and then checked
`0x1c9b4000..0x1cab4000`. The earlier window has one long zero run
(`0x1cab3e85..0x1cab4000`, 379 bytes) and no aligned complete zlib
stream within the 16 MiB decoded cap. Its endpoint candidates are:

| Candidate trailer, archive-relative | Child-relative | Observations |
| --- | --- | --- |
| `0x1caa4520..0x1cab3e90` | `0x282b520..0x283ae90` | No leading zero separator. The window ends 11 bytes into the zero run. |
| `0x1caa4690..0x1cab4000` | `0x282b690..0x283b000` | No leading zero separator. The window includes the entire 379-byte run. |

Neither start has the control's framing. The child header supplies the trailer
length, and an independent trailer start or parent entry offset/size is still
needed to determine the end. Keep this child unassigned in the extent index
until that evidence is available. The probe does not remap or extract the
archive.

```sh
python3 tools/data_last_child.py data.rpf
```
