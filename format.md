# Format ASCII

Every report is written to stdout as tab-separated ASCII/UTF-8 text. Records are
separated by a single LF. Fields are never quoted or escaped, so each line must
contain exactly the number of fields its header declares. Errors are a single
plain-text line on stderr with exit status 1; no report is written.

Conventions:

- Archive offsets, header words, and decoded offsets print as `0x` followed by
  lowercase hexadecimal without padding, for example `0x12a0`.
- Byte counts, entry counts, and stream counts print as decimal integers.
- Entropy prints as a decimal with four fractional digits, for example `7.7237`.
- A field that does not apply to a row is left empty, including any trailing
  empty fields.
- All offsets are absolute archive offsets. They are not pack-relative.
- Ranges are start-inclusive and end-exclusive.
- Extraction commands write the requested file with create-new semantics and
  refuse to overwrite an existing path.

### `inspect <archive>`

```text
archive_bytes	5632
header_offset	header_span	word_08	word_0c	word_24
0x0	0x340	0x310	0x90	4
```

`archive_bytes` is a one-row preface, not a column header. The `headers` table
then lists every page-aligned (`0x1000`) offset that begins with `9FPR` and whose
word at `+0x04` is a plausible span between `0x40` and the remaining bytes.

| Field | Meaning |
| --- | --- |
| `header_offset` | Absolute offset of the candidate `9FPR` header. |
| `header_span` | Header word at `+0x04`, the end of the front region. |
| `word_08` | Header word at `+0x08`, the candidate front-block boundary. |
| `word_0c` | Header word at `+0x0c`, the candidate trailer byte length. |
| `word_24` | Header word at `+0x24`, the count-like field. |

Field roles other than the magic remain interpretations of the observed samples.

### `map <archive> [<hex-start> <hex-end>]`

```text
kind	start	end	stored_bytes	decoded_bytes	chain_start
front	0x0	0x340	832		
zlib	0x340	0x4f1	433	800	0x340
zero_run	0x4f1	0x1000	2831		
trailer	0x1570	0x1600	144		
```

Rows partition the supplied pack range in ascending order with no gaps or
overlaps. `front` covers the pack start through the front-region end and is
always emitted. `trailer` covers the payload end through the pack end and is
emitted only when that extent is nonempty.

| `kind` | `stored_bytes` | `decoded_bytes` | `chain_start` |
| --- | --- | --- | --- |
| `front` | Span length | empty | empty |
| `zlib` | Stored zlib bytes | Checksum-verified decoded bytes | Offset of the first stream in the candidate chain |
| `zero_run` | Span length | empty | empty |
| `unclassified` | Span length | empty | empty |
| `trailer` | Span length | empty | empty |

A fresh chain has `chain_start` equal to its own `start`. Continuations keep the
`chain_start` of their predecessor. The map is an observation about stored
bytes; `unclassified` and `zero_run` are not decoded entry boundaries.

### `packs <archive> [<hex-start> <hex-end>]`

```text
header_offset	front_end	front_block_start	trailer_bytes	word_24	front_entropy	front_block_entropy	shared_0x40	trailer_start	trailer_entropy
0x0	0x340	0x310	144	4	7.7237	5.2933	true	0x1570	6.6681
```

One row per 16-byte-aligned `9FPR` header in the supplied range that is at
least `0x60` bytes long and has a front-block boundary and trailer inside the
pack bounds. `front_end` and `front_block_start` are absolute.
`trailer_bytes` and `word_24` are decimal header values. Entropy is Shannon
entropy in bits per byte:

| Field | Measured bytes |
| --- | --- |
| `front_entropy` | `+0x60` through `front_end` |
| `front_block_entropy` | `front_block_start` through `front_end` |
| `trailer_entropy` | `trailer_start` through the end of the supplied pack range |

`shared_0x40` is `true` when the 32 bytes at `+0x40..+0x60` match the archive's
own bytes at that range. `trailer_start` and `trailer_entropy` are filled only
for the selected pack at relative offset zero when `trailer_bytes` is nonzero;
nested headers and zero-length trailers leave both fields empty.

### `partition <archive> [<hex-start> <hex-end>]`

```text
metric	value
word_24	4
verified_streams	4
candidate_zlib_chains	4
opaque_spans	0
inferred_embedded_packs	0
unresolved_embedded_headers	0
candidate_entries	4
payload_bytes	4656
zlib_bytes	1795
opaque_bytes	0
inferred_embedded_bytes	0
zero_run_bytes	2861
count_comparison	match

candidate	start	end	span_bytes	decoded_bytes
zlib_chain	0x340	0x4f1	433	800
```

The first block is a `metric`/`value` table with these keys in this order:
`word_24`, `verified_streams`, `candidate_zlib_chains`, `opaque_spans`,
`inferred_embedded_packs`, `unresolved_embedded_headers`, `candidate_entries`,
`payload_bytes`, `zlib_bytes`, `opaque_bytes`, `inferred_embedded_bytes`,
`zero_run_bytes`, `count_comparison`. `count_comparison` is `match`, `over`, or
`under`, comparing `candidate_entries` with `word_24`.

A blank line and a second header follow. Candidates are listed in this order:
`embedded_rpf9`, `unresolved_rpf9_header`, `opaque`, then `zlib_chain` in
ascending start offset.

| `candidate` | Populated fields |
| --- | --- |
| `embedded_rpf9` | `start`, `end`, `span_bytes` |
| `unresolved_rpf9_header` | `start` holds the header offset; `end`, `span_bytes`, and `decoded_bytes` are empty |
| `opaque` | `start`, `end`, `span_bytes` |
| `zlib_chain` | `start`, `end`, `span_bytes`, `decoded_bytes` |

`decoded_bytes` is the sum over the chain's streams, not a per-stream value.
Embedded extents are kept only when a single tested end produces the child's
count-like field; otherwise the header is reported as unresolved and its bytes
remain in the parent scan.

### `list <archive>`

```text
offset	stored_bytes	decoded_bytes	magic
0xd6000	3378	5392	PSIN
```

One row per complete, checksum-verified zlib stream whose decoded payload starts
with `PSIN`. The scan advances in 16-byte steps and skips past accepted streams.
`magic` is currently always `PSIN`.

### `sections <archive> <hex-offset>`

```text
tag	decoded_offset	section_bytes
PSIN	0x0	86016
LSCH	0x15000	552
LENM	0x15228	128
LSNS	0x152a8	12724
LGID	0x1845c	8
LRSC	0x18464	88
CHKS	0x184bc	20
```

Rows walk the decoded PSIN payload. `tag` is four uppercase ASCII bytes,
`decoded_offset` is the section start within the decoded payload, and
`section_bytes` is the big-endian `u32` size field that includes the eight-byte
section header. A malformed tag, a size below 8, or a section that overruns the
payload aborts the command. The command joins a validated continuation stream
before parsing when the first stream decodes to exactly 64 KiB and has no
complete section list.

### `extract <archive> <hex-offset> <output>`

```text
0xe7000: 25483 stored bytes -> 99536 PSIN bytes
```

Writes the decoded PSIN payload to `output`. `stored_bytes` includes both zlib
streams and the zero padding between them. Continuation is accepted only when
the first stream decodes to 64 KiB, the next stream starts at the next 16-byte
boundary after zero padding, and the final `CHKS` section records the total
decoded length.

### `extract-zlib <archive> <hex-start> <hex-end> <output>`

```text
0x53000..0xc3b45: 42 zlib streams -> 2702384 decoded bytes
```

Validates every checksum, requires a full 64 KiB decoded chunk before each
continuation, checks intervening zero padding, then writes the concatenation.
`streams` counts accepted zlib streams.

### `extract-raw <archive> <hex-start> <hex-end> <output>`

```text
0x2010..0x52fe0: 331728 raw bytes
```

Copies the supplied range without interpretation. `raw bytes` is the range
length, which equals the written file size.

# Format JSON

The JSON form is the same report data as typed values instead of formatted
strings: offsets and sizes become unsigned integers, counts stay integers,
entropy stays a float, and empty ASCII fields are omitted. Ranges remain
start-inclusive and end-exclusive, and offsets remain absolute. The `kind`,
`candidate`, and `mode` discriminators are strings with the same spellings as
the ASCII first columns. Errors continue to go to stderr as text with exit
status 1, so callers must inspect the process status before parsing stdout.

The reports map to these Serde structs. `Cargo.toml` currently depends only on
`flate2`; implementation requires `serde` with the `derive` feature.
`Serialize` is required for output; add `Deserialize` only if a consumer needs
to read reports back. Field names match
the ASCII column names, and `#[serde(skip_serializing_if = "Option::is_none")]`
produces the same absent-field behavior as an empty ASCII field.

```rust
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct InspectReport {
    pub archive_bytes: usize,
    pub headers: Vec<InspectHeader>,
}

#[derive(Debug, Clone, Serialize)]
pub struct InspectHeader {
    pub header_offset: usize,
    pub header_span: usize,
    pub word_08: u32,
    pub word_0c: u32,
    pub word_24: u32,
}
```

```rust
#[derive(Debug, Clone, Serialize)]
pub struct MapReport {
    pub spans: Vec<MapSpan>,
}

#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SpanKind {
    Front,
    Zlib,
    ZeroRun,
    Unclassified,
    Trailer,
}

#[derive(Debug, Clone, Serialize)]
pub struct MapSpan {
    pub kind: SpanKind,
    pub start: usize,
    pub end: usize,
    pub stored_bytes: usize,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub decoded_bytes: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub chain_start: Option<usize>,
}
```

`decoded_bytes` and `chain_start` are `Some` only for `SpanKind::Zlib`. For
example, the `map` report for `story000_bvh4.rpf` begins:

```json
{
  "spans": [
    { "kind": "front", "start": 0, "end": 832, "stored_bytes": 832 },
    {
      "kind": "zlib",
      "start": 832,
      "end": 1265,
      "stored_bytes": 433,
      "decoded_bytes": 800,
      "chain_start": 832
    }
  ]
}
```

```rust
#[derive(Debug, Clone, Serialize)]
pub struct PacksReport {
    pub packs: Vec<PackReport>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PackReport {
    pub header_offset: usize,
    pub front_end: usize,
    pub front_block_start: usize,
    pub trailer_bytes: u32,
    pub word_24: u32,
    pub front_entropy: f64,
    pub front_block_entropy: f64,
    pub shared_0x40: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trailer_start: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trailer_entropy: Option<f64>,
}
```

`trailer_start` and `trailer_entropy` are `Some` only for the selected pack at
relative offset zero with a nonzero trailer length.

```rust
#[derive(Debug, Clone, Serialize)]
pub struct PartitionReport {
    pub summary: PartitionSummary,
    pub candidates: Vec<PartitionCandidate>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PartitionSummary {
    pub word_24: usize,
    pub verified_streams: usize,
    pub candidate_zlib_chains: usize,
    pub opaque_spans: usize,
    pub inferred_embedded_packs: usize,
    pub unresolved_embedded_headers: usize,
    pub candidate_entries: usize,
    pub payload_bytes: usize,
    pub zlib_bytes: usize,
    pub opaque_bytes: usize,
    pub inferred_embedded_bytes: usize,
    pub zero_run_bytes: usize,
    pub count_comparison: CountComparison,
}

#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CountComparison {
    Match,
    Over,
    Under,
}

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "candidate", rename_all = "snake_case")]
pub enum PartitionCandidate {
    EmbeddedRpf9 {
        start: usize,
        end: usize,
        span_bytes: usize,
    },
    UnresolvedRpf9Header {
        start: usize,
    },
    Opaque {
        start: usize,
        end: usize,
        span_bytes: usize,
    },
    ZlibChain {
        start: usize,
        end: usize,
        span_bytes: usize,
        decoded_bytes: usize,
    },
}
```

`UnresolvedRpf9Header.start` holds the header offset; the ASCII row leaves
`end`, `span_bytes`, and `decoded_bytes` empty. Candidates keep the ASCII order:
embedded packs, unresolved headers, opaque spans, then chains in ascending start
offset.

```rust
#[derive(Debug, Clone, Serialize)]
pub struct ListReport {
    pub streams: Vec<PsinStream>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PsinStream {
    pub offset: usize,
    pub stored_bytes: usize,
    pub decoded_bytes: usize,
    pub magic: PsinMagic,
}

#[derive(Debug, Clone, Copy, Serialize)]
pub enum PsinMagic {
    #[serde(rename = "PSIN")]
    Psin,
}
```

```rust
#[derive(Debug, Clone, Serialize)]
pub struct SectionsReport {
    pub sections: Vec<PsinSection>,
}

#[derive(Debug, Clone, Serialize)]
pub struct PsinSection {
    pub tag: String,
    pub decoded_offset: usize,
    pub section_bytes: usize,
}
```

`tag` stays a `String` because the parser accepts any four uppercase ASCII bytes,
not only the seven tags observed so far.

```rust
#[derive(Debug, Clone, Serialize)]
#[serde(tag = "mode", rename_all = "snake_case")]
pub enum ExtractionReport {
    Psin {
        offset: usize,
        stored_bytes: usize,
        decoded_bytes: usize,
    },
    Zlib {
        start: usize,
        end: usize,
        streams: usize,
        decoded_bytes: usize,
    },
    Raw {
        start: usize,
        end: usize,
        bytes: usize,
    },
}
```

`Psin` corresponds to `extract`, `Zlib` to `extract-zlib`, and `Raw` to
`extract-raw`. The output path is a command argument, not report data, so it is
not part of the struct.

## Annoyed Tools CLI

The separate `explorer/` crate provides bounded-memory tools. Offsets are
archive-relative and ends are exclusive. `annoyed-index [--resume] ARCHIVE
OUTPUT.tsv` creates a TSV with columns `kind`, `start`, `end`, `stored_bytes`,
`decoded_bytes`, `chain_start`, and `text_prefix`. Gaps remain unclassified;
this is a carved range index, not a decoded archive-entry table. `--resume`
uses adjacent checkpoint files and requires hard-link support for publication.

`annoyed-headers ARCHIVE` emits TSV columns `offset`, `front_bytes`,
`trailer_bytes`, and `declared_entries` for plausible page-aligned headers;
those observations do not establish pack boundaries. `annoyed-search ARCHIVE
INDEX.tsv TEXT` emits `start`, `end`, and `decoded_bytes` for zlib streams
containing exact case-sensitive UTF-8 bytes, followed by `kind` to distinguish
checksummed zlib from raw DEFLATE. `annoyed-extract raw|zlib|deflate ARCHIVE
START END OUTPUT` writes one range to a new file and reports its byte count.

`annoyed-verify [--progress] [--expect BASELINE.tsv] ARCHIVE INDEX.tsv` emits tab-separated key/value lines:
`ranges`, `zlib_streams`, `raw_deflate_streams`, `archive_bytes`, `unclassified_bytes`,
`unchecked_bytes`, `archive_sha256`, and `index_sha256`. Coverage, zlib
checksums and decoded sizes, raw-DEFLATE termination and decoded sizes, and
zero-run contents are checked. Raw DEFLATE carries no checksum. The hashes are
baselines; they do not prove entry identity, and unchecked bytes have no
zlib/zero content check. `--expect` requires both hashes to match a prior report.
