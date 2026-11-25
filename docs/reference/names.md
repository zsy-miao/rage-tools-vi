# Hash names

Every identifier in the object graph, in bone tables and in weight arrays is
`JOAAT(lowercase(name))` — a 32-bit hash with no inverse. Names are recovered by
*vocabulary*: hash candidate strings and keep the ones that collide with a value the
game actually stores.

This is **not** the archive's entry-name hash. That one is Murmur3 x64-128 over a
lower-cased name, and the 16-bit id it resolves to comes from a runtime dictionary —
see [the executable as a source](executable.md). JOAAT names content; the other names
files.

## The registry

`handoff/names.tsv` merges every recovered name:

| Column | Meaning |
| --- | --- |
| `hash` | `0x` + eight hex digits |
| `name` | the spelling the source gives |
| `kind` | `bone`, `weight`, `property/key`, `rig`, `meta` |
| `confidence` | `curated` > `meta` > `grammar` > `corpus` > `candidate` |
| `source` | the table the name came from |
| `also_known_as` | other spellings seen for the same hash |
| `ambiguous` | 1 when two *different real strings* share the hash |

36,952 names today: 36,305 from the engine's metadata table, 543 from corpus
sweeps, 64 curated, 39 from naming grammar, 1 candidate.

## Three commands

```bash
# what is this hash?
python3 tools/name_registry.py --lookup 0x01166164

# add name columns to any TSV with a hash column
python3 tools/name_registry.py --annotate handoff/script-bones.tsv \
    --column bone_hash --out handoff/script-bones-named.tsv

# read a script's schema instead of hex
python3 tools/psin_dump.py --record 110
```

`tools/annotate_handoff.py` does the second step for the whole handoff directory
and writes `handoff/name-coverage.tsv`, which records how many values each table
gained a name for.

## Why confidence matters

A hash can be named by more than one source, and the sources disagree in two
different ways:

- **case only** — `Position` (engine metadata) against `position` (corpus). Same
  name, so the higher-confidence spelling wins and nothing is lost.
- **two real strings** — `ABON_YEA` and `CVA_WHEEL_REAR_LEFT` really do share
  `0xbbb029a6`. That is a JOAAT collision, not an error, and the registry marks
  the row `ambiguous` instead of pretending one is right.

Across the 267 hashes named by both the engine table and the corpus sweeps, 261
agree (98 %); the remaining 6 are collisions.

## What is still unnamed

- **Type hashes** (`root_type`, `type_tag`): 0 hits from the 174k corpus, 4
  doubtful hits out of 234,720 `id1` values from the metadata table, and 0 from
  40 engine class names. This namespace is neither model strings nor metadata
  names, so it is most likely stored as text inside the `LSNS` tables.
- **14,138 PSIN object keys** and 276 properties, with the corpus vocabulary
  exhausted.
