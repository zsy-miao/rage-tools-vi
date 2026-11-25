# Extraction pipeline

This is the operational path from an RPF9 file to a report, a decoded stream, or
a verified payload. The Rust CLI owns the byte-level gates; Python analysis
consumes the results.

## End-to-end sequence

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant CLI as rage-tools-vi
    participant A as Archive
    participant Z as zlib / flate2
    participant O as output
    participant P as Python tools

    U->>CLI: inspect archive
    CLI->>A: scan page-aligned 9FPR headers
    CLI-->>U: header table
    U->>CLI: packs / map / partition
    CLI->>A: read header words and payload
    CLI->>Z: verify each zlib stream
    Z-->>CLI: checksum-valid chunks
    CLI-->>U: spans and candidate entries
    U->>CLI: extract-zlib start end output
    CLI->>Z: decode aligned chain
    Z-->>CLI: decoded bytes
    CLI->>O: create-new output
    CLI-->>U: stream count and decoded size
    U->>P: parse report / decoded bytes
    P-->>U: names, arrays, tables
```

## Gate order

```mermaid
flowchart TD
    S[input bytes] --> M{starts with 9FPR?}
    M -- no --> E[error]
    M -- yes --> H[read header words]
    H --> B{front/trailer bounds valid?}
    B -- no --> E
    B -- yes --> P[payload range]
    P --> Z{16-byte-aligned zlib header?}
    Z -- no --> G[zero_run or unclassified span]
    Z -- yes --> C{checksum valid?}
    C -- no --> G
    C -- yes --> F{decoded == 64 KiB?}
    F -- yes --> N[next aligned offset; zero padding]
    N --> Z
    F -- no --> D[accept chain]
    D --> R[report span or write output]
    G --> R
```

## Continuation rule

A stream continues only when:

1. the first decoded chunk is exactly `64 KiB`;
2. the next stream starts at the next 16-byte boundary after the previous
   stored stream;
3. every byte in the intervening padding is zero;
4. the final PSIN continuation has a valid `CHKS` section whose length matches
   the decoded total.

```mermaid
stateDiagram-v2
    [*] --> FirstStream
    FirstStream --> Short: decoded != 64 KiB
    FirstStream --> Full: decoded == 64 KiB
    Full --> Aligned: next multiple of 16
    Aligned --> Padded: all padding bytes zero
    Padded --> NextStream
    NextStream --> Short: final chunk
    NextStream --> Full: another full chunk
    Short --> [*]: accept and write
    Full --> [*]: reject unterminated chain
    Aligned --> [*]: bad padding
```

## Report → artifact

```mermaid
flowchart LR
    I[inspect] --> IH[header inventory]
    M[map] --> MS[span map]
    P[packs] --> PE[entropy / trailer bounds]
    D[partition] --> DC[candidate entries]
    S[sections] --> ST[section table]
    X[extract-zlib] --> OBJ[object bytes]
    OBJ --> PY[Python graph tools]
    PY --> TSV[handoff TSVs]
    IH --> DOC[plan / investigation]
    MS --> DOC
    PE --> DOC
    DC --> DOC
    ST --> DOC
```

## CLI examples

```bash
# Header inventory
target/debug/rage-tools-vi inspect script.rpf

# Partition and report the count comparison
target/debug/rage-tools-vi partition script.rpf

# Decode the 42-stream object
target/debug/rage-tools-vi extract-zlib \
  script.rpf 0x53000 0xc3b45 /tmp/object.bin

# Copy the parked blob literally
target/debug/rage-tools-vi extract-raw \
  script.rpf 0x2010 0x52fe0 /tmp/blob.bin
```

!!! note "Exclusive ends and absolute offsets"
    Every `start..end` range is start-inclusive, end-exclusive, and absolute.
    Extraction refuses to overwrite an existing output path.
