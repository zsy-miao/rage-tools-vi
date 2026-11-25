# Localization

Localization is the most complete plaintext corpus in the archive. It gives
known strings, language order, and group boundaries that can be used as cribs
for otherwise opaque metadata.

## Pack structure

```mermaid
flowchart LR
    P["language pack"] --> G["1,115 minimum-padding zlib groups"]
    G --> T["UTF-8 text entries"]
    T --> X["localized/text.tsv"]
    P --> R["29,856-byte trailer"]
    R --> S["13 identical trailers"]
```

## Entity model

```mermaid
erDiagram
    ARCHIVE ||--o{ LANGUAGE_PACK : contains
    LANGUAGE_PACK ||--o{ ZLIB_GROUP : groups
    ZLIB_GROUP ||--o{ TEXT : decodes
    LANGUAGE_PACK ||--|| TRAILER : ends_with
    LANGUAGE_PACK {
        string language
        uint32 groups
        uint32 trailer_bytes
    }
    ZLIB_GROUP {
        uint32 ordinal
        uint32 stored_bytes
        uint32 decoded_bytes
    }
    TEXT {
        string key
        string value
        string language
    }
    TRAILER {
        uint32 bytes
        string sha256
    }
```

## Language order

The localization payloads identify every language in the order declared by
`core_language`. The observed set includes `american`, `brazilian`, and
`german`; the shared trailer makes the packs a cohort.

```mermaid
sequenceDiagram
    autonumber
    participant A as Analyst
    participant L as Language pack
    participant Z as zlib
    participant T as text.tsv

    A->>L: read pack header and group count
    L->>Z: decode 1,115 groups
    Z-->>L: UTF-8 entries
    L->>T: index by language/key
    A->>L: compare 29,856-byte trailers
    L-->>A: shared trailer hash
```

## Crib value

```mermaid
flowchart TD
    TXT[known localization strings] --> H[JOAAT / token dictionary]
    H --> N[name roots and parts]
    TXT --> E[known plaintext extents]
    E --> F[Front A / trailer tests]
    N --> G[object graph]
```

## Open questions

- Is the shared trailer a deterministic build-wide value or a localization
  table?
- Can the group ordinals predict any Front A field?
- Does the language order break the `N mod 4 = 0` metadata ambiguity?
