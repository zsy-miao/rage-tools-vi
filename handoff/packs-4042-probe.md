# u16_4042 probe

The dominant packs family is 28,713 streams / 5,434,544,304 bytes with header
`42 40 00 00` (little-endian u16 `0x4042`). It has 2,992 distinct sizes.

## Size classes

| Size | Streams |
| ---: | ---: |
| 1,040 | 2,535 |
| 393,216 | 2,291 |
| 131,072 | 2,155 |
| 851,968 | 1,513 |
| 256 | 1,450 |
| 196,608 | 1,009 |
| 262,144 | 930 |
| 25,424 | 919 |
| 327,680 | 870 |
| 65,536 | 730 |

The large classes are 64 KiB multiples, consistent with resource payloads;
1,040/256/25,424/25,440/41,840/51,424 are metadata-like sizes.

## Header words

After `0x4042`, the small words recur in families ending `0x21`, `0x28`,
`0x26`, and `0x25`:

- `0x0000a421` (2,537)
- `0x00070821` (1,654)
- `0x00099c21` (1,639)
- `0x00016c28` (2,535)
- `0x00222828` (1,650)
- `0x00005e28` (1,450)
- `0x0000d626` (2,866)
- `0x00010825` (2,868)

They are **not file offsets**: the plausible-offset count is 0 for most words.
The low byte is likely a type/class tag, not a length. The first 1,040-byte
group is byte-identical across at least eight streams, so metadata is shared.

## Next

Test whether the 64 KiB-multiple classes are textures or audio by correlating
their size classes with known dimensions/codecs, and probe the `0x...21/26/28/25`
low-byte families as type tags.

Artifact: `handoff/packs-4042-probe.tsv`; tool: `tools/probe_4042.py`.
