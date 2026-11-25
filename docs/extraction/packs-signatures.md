# packs.rpf signature survey

After full extraction, every stream is classified by its first non-zero
signature. This is a semantic map, not a full decode.

| Kind | Streams | Decoded bytes |
| --- | ---: | ---: |
| binary | 113,480 | 4,247,446,132 |
| `u16_4042` | 28,713 | 5,434,544,304 |
| `0f000080` | 1,148 | 11,692,416 |
| PSIN | 586 | 10,854,064 |
| XML? | 386 | 29,818,040 |
| zero | 47 | 850,688 |
| zlib | 5 | 187,424 |
| RBF0 | 1 | 215 |

`u16_4042` is the dominant non-binary family: 28,713 streams / 5.43 GB. The
`0f000080` family is 1,148 streams. Both headers remain unnamed. The PSIN/XML
population is small but already parseable.

```bash
python3 tools/signature_survey.py \
  output/extracted/packs/manifest.tsv
```

Artifacts: `handoff/packs-signature-summary.tsv`; detailed local table
`output/packs-signatures.tsv`.

### `u16_4042` probe

28,713 streams / 2,992 distinct sizes; 64 KiB-multiple size classes and small
recurring header words ending `0x21`, `0x26`, `0x28`, `0x25`. Those words are not
file offsets; the low byte is likely a type/class tag. The 1,040-byte group is
byte-identical across streams.

Report: `handoff/packs-4042-probe.md`; data: `handoff/packs-4042-probe.tsv`;
tool: `tools/probe_4042.py`.

Size-class behavior splits into metadata-like 1,040/256, high-entropy
393,216/851,968/524,288, and structured 131,072/196,608/262,144/65,536 classes.
See `handoff/packs-4042-classes.md` and `tools/probe_4042_classes.py`.

### `0f000080` probe

1,148 streams / 11,692,416 bytes, almost all 9.9–10.1 KiB. Header words are
`0x8000000f`, count-like `0x62a`, count-like `0x6b5..bc`, then packed data.
Entropy is ~6.9 bits/byte; the 16-bit stream uses the full range. It is a
compact quantized payload, likely geometry/navmesh or animation; name open.

Report: `handoff/packs-0f000080-probe.md`; data:
`handoff/packs-0f000080-probe.tsv`; tool: `tools/probe_0f000080.py`.

### ML clustering pilot

113,480 binary streams clustered into 32 byte-feature families. The largest
families are zero-prefixed `...0050` tables; visible subgroups include
`GM_U01_C`, `0x4040`, `0e000080`, and float-like headers. This is a proposal
engine, not a verifier.

Report: `handoff/packs-binary-clusters.md`; summary:
`handoff/packs-binary-clusters.tsv`; tool: `tools/ml_binary_clusters.py`.

Active-learning queue: 128 representatives / 32 clusters, four variants each.
Label the `label` column in `handoff/packs-label-queue.tsv`; generator:
`tools/active_learning_queue.py`.
