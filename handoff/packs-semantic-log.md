# packs semantic log

Date: 2026-11-20
Scope: full extraction of `packs.rpf` and post-extraction semantic probes.
No duplicate data/DeepSeek extraction jobs.

## Extraction

- 144,366 zlib streams; 9,735,393,283 decoded bytes.
- Output: `output/extracted/packs`
- Verification: 144,366/144,366; missing 0; extra 0; failures 0.
- Manifest: `packs/manifest.tsv`; verification summary:
  `handoff/bulk-extraction-verification-summary.tsv`.

## Signature survey

| Kind | Streams | Decoded bytes |
| --- | ---: | ---: |
| binary | 113,480 | 4,247,446,132 |
| u16_4042 | 28,713 | 5,434,544,304 |
| 0f000080 | 1,148 | 11,692,416 |
| PSIN | 586 | 10,854,064 |
| XML? | 386 | 29,818,040 |
| zero | 47 | 850,688 |
| zlib | 5 | 187,424 |
| RBF0 | 1 | 215 |

Artifact: `handoff/packs-signature-summary.tsv`.

## u16_4042

- 28,713 streams; 2,992 sizes.
- Metadata-like: 1,040/256 (entropy 2.8–3.0; zero 0.57–0.63).
- High-entropy: 393,216/851,968/524,288 (entropy ~7.97–7.98).
- Structured: 131,072/196,608/262,144/65,536 (entropy 5.2–6.2).
- Header words end 0x21/0x26/0x28/0x25; not file offsets; low-byte
  type-tag hypothesis.
- 1,040-byte group is byte-identical across streams.

Artifacts: `handoff/packs-4042-probe.md`, `handoff/packs-4042-probe.tsv`,
`handoff/packs-4042-classes.md`, `handoff/packs-4042-classes.tsv`.

## 0f000080

- 1,148 streams / 11,692,416 bytes; almost all 9.9–10.1 KiB.
- Header `0x8000000f`, count-like `0x62a`, `0x6b5..bc`.
- Entropy ~6.9; full-range 16-bit payload.
- Hypothesis: compact quantized geometry/navmesh or animation; name open.

Artifacts: `handoff/packs-0f000080-probe.md`,
`handoff/packs-0f000080-probe.tsv`.

## Tools

`bulk_extract.py`, `verify_bulk.py`, `signature_survey.py`, `probe_4042.py`,
`probe_4042_classes.py`, `probe_0f000080.py`, `stream_index.py`,
`mmap_extract.py`.
