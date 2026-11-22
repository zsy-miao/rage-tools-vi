# Story000 BVH4 entry-to-payload check

Bus handoff #0143, 2026-11-21. All ranges are archive-relative and end-exclusive.

**Result:** Entry-to-payload proof remains open. The little-endian RPF9 header
locates the metadata regions. The entry bytes that would identify a payload
start and stored length or end are still undecoded. Their record boundaries,
endianness and any transform are unverified.

## Independent range targets

The mounted 5,632-byte control is byte-identical to the repository's local
`story000_bvh4.rpf` (SHA-256
`b9f86219f835c769ca86274f933ab35423af45dad33f130d5c5e4727450ffd24`).
The Rust map reproduced the exact ranges below. The independent zlib, XML and
SHA-256 checks are in [story000-bvh4-control.tsv](story000-bvh4-control.tsv).

| Start | End | Stored bytes | Decoded bytes |
| --- | --- | ---: | ---: |
| `0x340` | `0x4f1` | 433 | 800 |
| `0x1000` | `0x1291` | 657 | 14,426 |
| `0x12a0` | `0x13bd` | 285 | 622 |
| `0x13c0` | `0x1564` | 420 | 829 |

The story header at `+0x04` contains `40 03 00 00`, which decodes to
`0x340`, where the front ends and the first XML stream happens to begin with
`78 da`. In the only secondary control, `core_licenses_data.rpf`, the same
field is `30 03 00 00` and points to `0x330`. The range
`0x330..0x1000` there is all zero, followed by an embedded RPF9 at `0x1000`.
The end of the first story stream, `0x4f1`, comes from successful inflation
through the zlib checksum. The header field alone yields neither endpoint of
that stream as a general entry formula.

## Table evidence

The small controls have the same count (`u32le(+0x24) = 4`) and the
same Front B and trailer lengths, while their payload ranges differ.

| Candidate region | Story range | Core range | Story fields tested | Core fields tested |
| --- | --- | --- | ---: | ---: |
| Front A | `0x60..0x310` | `0x60..0x300` | 2,078,548 | 2,133,288 |
| Front B | `0x310..0x340` | `0x300..0x330` | 88,787 | 88,978 |
| Trailer | `0x1570..0x1600` | `0x3450..0x34e0` | 1,232,400 | 1,231,395 |

The fixed-stride probe checks 6- to 32-bit fields at every bit offset in both
byte orders. It looks for all four starts, allowing any row order, archive or
front-end base, and byte through 32-byte units when lossless. It tests direct,
common additive bias, and common XOR representations. Front A was tested
at strides of 8, 10, 12, 16, 20, 24, 32 and 48 bytes. Front B and the trailer
used every stride of at least four bytes that fits four fields. The core targets
include one independently mapped embedded pack envelope and three zlib streams.
The result is **zero four-start fields and zero offset/size pairs** in either
control. Size-only matches in story's trailer and core's Front A provide no
entry-to-range proof.

A synthetic positive check replaced the first 40 Front A bytes in a temporary
copy of story with four 10-byte `<II2x` records containing the verified starts
and stored sizes in archive order. The 10-byte probe recovered one compatible
plain row order with little-endian starts at bit 0. The real archive was
unchanged.

The first 32 trailer bytes also match byte-for-byte across the controls
(`5a178c51e7b96189237e72453084db8a 18415cbd0e16c0d303e94434e40de9ad`).
At the same position they cannot encode a complete varying range table on
their own without another input. The suffix begins with `ab c7 3d d3` in story
and `a0 fe 4d b2` in core. These bytes establish a shared-prefix boundary.
The probe does not identify a cipher, key, IV or even a confirmed ciphertext
boundary. In particular, splitting Front A at `0x160` remains a hypothesis.

Reopen with an independently identified table span and its decoding parameters,
or a plaintext record with a documented offset plus stored size or end. Parse
that record before reading the payload, then compare its predicted range and
decoded SHA-256 against the control TSV.

## Reproduce

```sh
story='/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK/pack/story000_bvh4/story000_bvh4.rpf'
cmp story000_bvh4.rpf "$story"
target/debug/rage-tools-vi map "$story"
target/debug/rage-tools-vi map core_licenses_data.rpf
for archive in "$story" core_licenses_data.rpf; do
  python3 tools/probe_index_layout.py "$archive" \
    --region front-a --stride 8 --stride 10 --stride 12 --stride 16 \
    --stride 20 --stride 24 --stride 32 --stride 48
  python3 tools/probe_index_layout.py "$archive"
done
```
