# Architecture overview

The project has four layers: **byte access**, **reporting**, **object-graph
analysis**, and **corpus-specific extraction**. The Rust CLI owns byte access
and checksum validation; Python tools own naming, graph traversal, and
experiments; the handoff and journals are the integration surface.

## Component view

```mermaid
flowchart TB
    subgraph External["External inputs"]
        RPF[RPF9 archives]
        XML[Decoded XML / localization]
        BONE[data.rpf bone corpus]
    end

    subgraph CLI["Rust CLI · src/"]
        MAIN[main.rs<br/>dispatch and zlib]
        MAP[range_map.rs<br/>span accounting]
        PART[partition.rs<br/>candidate ranges]
        PACK[pack_report.rs<br/>header entropy]
        EXT[range_extract.rs<br/>aligned chains]
    end

    subgraph Tools["Python · tools/"]
        NAMES[root_names.py · object_names.py]
        GRAPH[property_tree.py · root_classes.py]
        ARR[array_types.py · bone_table.py]
        META[front_a_*.py · localized_extents.py]
        DATA[native_texture_scan.py · texture_decode.py]
    end

    subgraph Artifacts["Artifacts"]
        REP[stdout ASCII / JSON]
        TSV[handoff/*.tsv]
        DOC[plan.md · investigation.md]
    end

    RPF --> MAIN
    MAIN --> MAP --> PART
    MAIN --> PACK
    MAIN --> EXT
    XML --> NAMES --> GRAPH
    BONE --> GRAPH
    RPF --> GRAPH
    GRAPH --> ARR
    META --> DOC
    RPF --> META
    DATA --> TSV
    ARR --> TSV
    REP --> TSV
    NAMES --> TSV
    TSV --> DOC
```

## Runtime sequence

```mermaid
sequenceDiagram
    autonumber
    participant U as User / analyst
    participant C as rage-tools-vi
    participant A as Archive bytes
    participant T as Python tool
    participant H as handoff/ or journal

    U->>C: inspect / partition / extract
    C->>A: read archive
    C->>C: validate magic, spans, zlib checksums
    C-->>U: ASCII or JSON report
    U->>T: feed report or known offsets
    T->>A: extract object range
    T->>T: traverse records / arrays / names
    T-->>U: table or candidate
    U->>H: record evidence and handoff
```

## Module responsibilities

| Module | Owns | Does not own |
| --- | --- | --- |
| `src/main.rs` | CLI dispatch, zlib decode, top-level reports | object semantics |
| `src/range_map.rs` | byte partitioning, chain starts | archive index meaning |
| `src/partition.rs` | candidate entries vs `+0x24` | directory-node proof |
| `src/pack_report.rs` | header words, entropy, trailer bounds | trailer record meaning |
| `src/range_extract.rs` | 16-byte aligned zlib continuation | payload semantics |
| `tools/*.py` | names, records, arrays, experiments | canonical byte extraction |
| `handoff/` | exchanged tables | source of truth for the format |

## Deployment and reproducibility

```mermaid
flowchart LR
    SRC[git checkout] --> CARGO[cargo build]
    SRC --> VENV[python venv]
    CARGO --> BIN[target/debug/rage-tools-vi]
    VENV --> TOOLS[python3 tools/*.py]
    BIN --> TOOLS
    TOOLS --> OUT[output/ · handoff/]
    SRC --> MKDOCS[mkdocs build]
    MKDOCS --> SITE[site/ · untracked]
```

!!! warning "Samples are local"
    The `*.rpf` files are large and untracked. Documentation diagrams describe
    their structure, not a distributable corpus.
