# data.rpf

`data.rpf` is the large corpus: localization, textures, credits, metadata, and
named resources. It is the primary place to borrow names and layouts for the
script object.

## Corpus map

```mermaid
flowchart TB
    ROOT["data.rpf<br/>42 headers<br/>28,509 verified streams"] --> LOC["13 localization packs<br/>N = 1,115 groups each"]
    ROOT --> TX["texture dictionaries<br/>788 textures"]
    ROOT --> CR["credits child @0x964000<br/>156 raw DEFLATE streams"]
    ROOT --> NR["named resources @0x1228e000<br/>2,502 names"]
    ROOT --> BA["vehicle/bone corpus<br/>PSIN records"]
    ROOT --> OP["opaque spans<br/>child ends pending"]

    LOC --> LANG["american · brazilian · german<br/>and declared languages"]
    TX --> FMT["formats 0x4D · 0x62<br/>mip/tile open"]
    CR --> RBF["136 credits pages<br/>20 RBF0 configurations"]
    NR --> WPN["1,075 .#dr · 1,427 .#ft<br/>weapon model/component names"]
```

## Stream accounting

| Metric | Value | State |
| --- | ---: | --- |
| top-level archives | 6 | inventory |
| checksum streams | 30,527 | verified |
| `data.rpf` streams | 28,509 | verified |
| plausible headers | 42 | candidate |
| carved child packs | 40 | candidate |
| default PSIN chains | 2,281 | 2,256 complete |
| decoded RBF0 chains | 1,260 | readable roots |
| texture dictionaries | 73 | valid |
| textures | 788 | descriptor-valid |

## UML view

```mermaid
classDiagram
    class DataArchive {
        +bytes: 481,544,304
        +headers: 42
        +streams: 28,509
    }
    class LocalizationPack {
        +languages: 13
        +groups_per_pack: 1,115
        +trailer_bytes: 29,856
        +trailer_sha: shared
    }
    class TextureDictionary {
        +textures: 788
        +formats: 0x4D_0x62
        +manifest: manifest.tsv
    }
    class CreditsPack {
        +offset: 0x964000
        +streams: 156
        +pages: 136
    }
    class NamedResourceSet {
        +offset: 0x1228e000
        +names: 2,502
    }
    DataArchive "1" *-- "13" LocalizationPack
    DataArchive "1" *-- "1..*" TextureDictionary
    DataArchive "1" *-- "1" CreditsPack
    DataArchive "1" *-- "1" NamedResourceSet
```

## Localization ER

```mermaid
erDiagram
    ARCHIVE ||--o{ LANGUAGE_PACK : contains
    LANGUAGE_PACK ||--o{ GROUP : has
    GROUP ||--o{ TEXT_ENTRY : stores
    LANGUAGE_PACK ||--|| TRAILER : ends_with
    LANGUAGE_PACK {
        string language
        uint32 groups
        uint32 trailer_bytes
    }
    GROUP {
        uint32 ordinal
        uint32 decoded_bytes
    }
    TEXT_ENTRY {
        string key
        string value
    }
    TRAILER {
        uint32 bytes
        string shared_hash
    }
```

## Credits and named resources

```mermaid
sequenceDiagram
    autonumber
    participant A as Analyst
    participant C as Credits child
    participant D as Raw DEFLATE
    participant N as Named resources
    participant H as handoff/

    A->>C: bound child at 0x964000
    C->>D: decode 156 streams
    D-->>C: 136 pages + 20 RBF0 configs
    A->>N: scan 0x1228e000 pointers
    N-->>A: 2,502 names
    A->>H: publish tables and roots
```

## Skeleton-family negative

The 16 class-0 skeleton families do not match the pointed resource-name corpus
or the harvested PSIN names: 0/44 roots and 0/612 bone hashes. A model/layout
mapping needs an independently decoded ordered skeleton.

## Open boundaries

The final child end at `0x1a279000` and opaque streams near `0x120d7000`
remain open. The 13 localization packs share identical 29,856-byte trailers,
which is a cohort observation, not yet a cross-archive law.
