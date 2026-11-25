# RPF9 container format

The observed archive begins with the little-endian magic bytes `9FPR` (the
ASCII spelling `RPF9` is used throughout the code). The observed first header is
`0x60` bytes. The code validates at least the first `0x40` bytes for payload
operations. A pack has three metadata regions and a payload region.

## Byte layout

```mermaid
flowchart LR
    H["Header<br/>0x60 bytes"] --> A["Front A<br/>0x60 → word_08"]
    A --> B["Front B<br/>word_08 → word_04"]
    B --> P["Payload<br/>zlib chains · zero runs · opaque spans"]
    P --> T["Trailer<br/>end - word_0c → end"]
```

All four boundaries are 16-byte aligned in the observed samples. The header
stores **absolute archive offsets**:

| Word | Offset | Role | Evidence |
| --- | ---: | --- | --- |
| `word_04` | `+0x04` | `front_end` | end of Front B |
| `word_08` | `+0x08` | Front A/B boundary | `align16(9N)`/`align16(10N)` from it in mode family 1 |
| `word_0c` | `+0x0c` | trailer byte length | equals the trailer length in 4,373/4,373 headers |
| `word_24` | `+0x24` | entry count N | Front B law fits every family-1 header |
| `word_2c` | `+0x2c` | entry format tag | 2 values, split at N = 255/256 |
| `word_34..3c` | `+0x34..+0x3c` | zero | constant |
| shared | `+0x40..+0x4c` | 16-byte constant block | identical across all 4,373 headers |
| profile | `+0x50..+0x5c` | profile block | 4 values |

Full word map, size laws, and masking evidence: [Metadata regions](metadata.md).

## UML view of a pack

```mermaid
classDiagram
    class Archive {
        +bytes: Vec~u8~
        +magic: 9FPR
        +packs: List~Pack~
    }
    class Pack {
        +header_offset: usize
        +front_end: usize
        +front_block_start: usize
        +trailer_bytes: u32
        +word_24: u32
        +payload_range() Range
    }
    class MetadataRegion {
        +name: BufferA_BufferB_Trailer
        +start: usize
        +end: usize
        +alignment: 16
        +reading: verbatim copy
        +layout: arena header + five regions
    }
    class Span {
        +kind: SpanKind
        +start: usize
        +end: usize
        +stored_bytes: usize
        +decoded_bytes: Option~usize~
        +chain_start: Option~usize~
    }
    class SpanKind {
        <<enumeration>>
        Front
        Zlib
        ZeroRun
        Unclassified
        Trailer
    }
    Archive "1" *-- "1..*" Pack
    Pack "1" *-- "3" MetadataRegion
    Pack "1" *-- "0..*" Span
    Span --> SpanKind
```

## Span accounting

`map` partitions the pack range in ascending order without gaps or overlaps.
A fresh zlib chain has `chain_start == start`; a continuation keeps the first
stream's `chain_start`.

```mermaid
flowchart TD
    S[pack start] --> F[front span]
    F --> Z{zlib header<br/>at aligned offset?}
    Z -- yes --> C[decode and validate checksum]
    C --> C2{decoded chunk == 64 KiB?}
    C2 -- yes --> P[zero padding to next 16-byte boundary]
    P --> Z
    C2 -- no --> K[chain ends]
    Z -- no --> R{zero bytes?}
    R -- yes --> Q[zero_run]
    R -- no --> U[unclassified]
    Q --> Z
    U --> Z
    K --> T[trailer span]
    T --> E[pack end]
```

## Extraction state machine

```mermaid
stateDiagram-v2
    [*] --> AlignedStart
    AlignedStart --> Decoding: start % 16 == 0
    Decoding --> ChecksumOK: flate2 returns a full stream
    ChecksumOK --> Final: decoded chunk != 64 KiB
    ChecksumOK --> Continue: decoded chunk == 64 KiB
    Continue --> Padding: next 16-byte boundary
    Padding --> Decoding: padding is all zero
    Padding --> [*]: bad padding
    Final --> [*]: append and report
    Decoding --> [*]: checksum or framing error
```

## Archive → pack → stream

```mermaid
erDiagram
    ARCHIVE ||--o{ PACK : contains
    PACK ||--o{ SPAN : partitions
    PACK ||--o{ PSIN_STREAM : stores
    SPAN ||--o| PSIN_STREAM : zlib
    PACK {
        uint32 front_end
        uint32 front_block_start
        uint32 trailer_bytes
        uint32 word_24
    }
    SPAN {
        string kind
        uint32 start
        uint32 end
        uint32 stored_bytes
        uint32 decoded_bytes
        uint32 chain_start
    }
    PSIN_STREAM {
        uint32 offset
        uint32 stored_bytes
        uint32 decoded_bytes
        string magic
    }
```

## Metadata status

Front A, Front B, and the trailer are **not decoded**. They are 16-byte
multiples, the trailer behaves CBC-like, and the size tables are measured. No
key or plaintext name is recovered. See [Metadata regions](metadata.md) for the
negative results and the exact wall.
