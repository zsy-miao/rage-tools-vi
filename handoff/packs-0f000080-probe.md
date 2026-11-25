# 0f000080 probe

`0f000080` is a compact, high-entropy family: **1,148 streams / 11,692,416
bytes**, almost entirely 9.9–10.1 KiB.

| Header word | Common value | Reads as |
| --- | ---: | --- |
| `word_0` | `0x8000000f` | family magic |
| `word_1` | `0x0000062a` (1,094) | count-like, ~1,578 |
| `word_2` | `0x000006b5..bc` | count-like, ~1,717 |
| `word_3` | `0x30b2377f` etc. | packed data |
| `word_4` | `0` | reserved |
| `word_5` | `0x007fe7ff` | packed data |
| `word_6` | `0x00000808` / `0x00000807` | packed type tag? |
| `word_7` | `0x2e9f3fe1` etc. | packed data |

Entropy is about 6.9 bits/byte. The 16-bit stream uses the full 0..65535 range,
so it is quantized/compressed rather than plain floats. Size and count-like
words are consistent with a compact geometry/navmesh or animation payload; the
name remains open.

Artifact: `handoff/packs-0f000080-probe.tsv`; tool:
`tools/probe_0f000080.py`.
