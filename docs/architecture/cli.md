# Rust CLI and report model

The binary is intentionally small: it validates structure and emits typed
reports. It does not guess names or object semantics. The JSON contract is summarized in
[Report formats](../reference/report-formats.md); the canonical file is
`format.md` at the repository root.

## Commands

| Command | Scope | Main evidence |
| --- | --- | --- |
| `inspect` | page-aligned `9FPR` headers | header words |
| `map` | every byte in a pack range | front / zlib / zero / trailer spans |
| `packs` | nested packs | front entropy, trailer bounds |
| `partition` | candidate entries | chain/opaque count vs `+0x24` |
| `list` | PSIN zlib streams | decoded magic |
| `sections` | PSIN section walk | section tags and sizes |
| `extract` | PSIN payload | checksum + `CHKS` |
| `extract-zlib` | aligned stream chain | 64 KiB continuation rule |
| `extract-raw` | literal byte range | no interpretation |

## Report model

```mermaid
classDiagram
    direction LR
    class InspectReport {
        +archive_bytes: usize
        +headers: List~InspectHeader~
    }
    class InspectHeader {
        +header_offset: usize
        +header_span: usize
        +word_08: u32
        +word_0c: u32
        +word_24: u32
    }
    class MapReport {
        +spans: List~MapSpan~
    }
    class MapSpan {
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
    class PacksReport {
        +packs: List~PackReport~
    }
    class PackReport {
        +header_offset: usize
        +front_end: usize
        +front_block_start: usize
        +trailer_bytes: u32
        +word_24: u32
        +front_entropy: f64
        +front_block_entropy: f64
        +shared_0x40: bool
        +trailer_start: Option~usize~
        +trailer_entropy: Option~f64~
    }
    class PartitionReport {
        +summary: PartitionSummary
        +candidates: List~PartitionCandidate~
    }
    class PartitionSummary {
        +word_24: usize
        +verified_streams: usize
        +candidate_zlib_chains: usize
        +opaque_spans: usize
        +candidate_entries: usize
        +count_comparison: CountComparison
    }
    class PartitionCandidate {
        <<enumeration>>
        EmbeddedRpf9
        UnresolvedRpf9Header
        Opaque
        ZlibChain
    }
    class CountComparison {
        <<enumeration>>
        Match
        Over
        Under
    }
    class SectionsReport {
        +sections: List~PsinSection~
    }
    class PsinSection {
        +tag: String
        +decoded_offset: usize
        +section_bytes: usize
    }
    class ExtractionReport {
        <<enumeration>>
        Psin
        Zlib
        Raw
    }

    InspectReport "1" *-- "0..*" InspectHeader
    MapReport "1" *-- "0..*" MapSpan
    MapSpan --> SpanKind
    PacksReport "1" *-- "0..*" PackReport
    PartitionReport "1" *-- "1" PartitionSummary
    PartitionReport "1" *-- "0..*" PartitionCandidate
    PartitionSummary --> CountComparison
    SectionsReport "1" *-- "0..*" PsinSection
```

`MapSpan.decoded_bytes` and `chain_start` are present only for `Zlib`.
`PackReport.trailer_start` and `trailer_entropy` are present only for the
selected pack at relative offset zero with a nonzero trailer. In JSON the
tagged enums use `kind`, `candidate`, `mode`, and `count_comparison` as
discriminators.

## Command dispatch

```mermaid
stateDiagram-v2
    [*] --> Parse
    Parse --> Help: --help / -h
    Parse --> ReadArchive: valid command/path
    Parse --> Error: arity or unknown command
    ReadArchive --> Error: missing 9FPR magic
    ReadArchive --> Inspect: inspect
    ReadArchive --> Map: map
    ReadArchive --> Packs: packs
    ReadArchive --> Partition: partition
    ReadArchive --> List: list
    ReadArchive --> Sections: sections
    ReadArchive --> Extract: extract
    ReadArchive --> ExtractZlib: extract-zlib
    ReadArchive --> ExtractRaw: extract-raw
    Inspect --> Report
    Map --> Report
    Packs --> Report
    Partition --> Report
    List --> Report
    Sections --> Report
    Extract --> Report
    ExtractZlib --> Report
    ExtractRaw --> Report
    Report --> [*]
    Help --> [*]
    Error --> [*]
```

## Aligned zlib extraction

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant CLI as rage-tools-vi
    participant Z as flate2
    participant F as output file

    U->>CLI: extract-zlib archive start end output
    CLI->>CLI: require 16-byte-aligned start
    loop each stream in the chain
        CLI->>Z: decode checksum-valid zlib
        Z-->>CLI: stored bytes + decoded chunk
        alt chunk is exactly 64 KiB and more bytes remain
            CLI->>CLI: advance to next 16-byte boundary
            CLI->>CLI: require zero padding
        else final chunk
            CLI->>F: append decoded bytes
            CLI-->>U: streams + decoded_bytes
        end
    end
```

!!! note "Design boundary"
    `extract-zlib` validates framing and checksums. It deliberately does not
    interpret `PSIN`, `LSCH`, `LSNS`, or any object record.
