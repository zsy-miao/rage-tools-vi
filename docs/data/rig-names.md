# Rig names and hash namespaces

Every identifier recovered so far is `JOAAT(lowercase name)`, the one-at-a-time
hash Rockstar uses elsewhere. That makes any candidate name testable against a
hash in one line, and it means a namespace can be opened by finding its
*vocabulary*, not its algorithm.

## Bone tables and weights share one namespace

The class-0 bone tables hold 612 distinct hashes over 3,043 bone slots. Generating
`<skel_|mh_|rb_><side><part><00–99>` over a curated anatomy vocabulary resolves
**99 of 612**, and the same generator resolves **21 of 252** hashes in the
`0x8f18aff0` weight arrays. Seventeen names appear in both, so the weight arrays
are blend weights over named bones.

| Family | Meaning | Table names | Weight names |
| --- | --- | ---: | ---: |
| `skel_` | skeleton bones | 36 | 5 |
| `mh_` | muscle helpers | 43 | 12 |
| `rb_` | ragdoll bodies | 20 | 4 |

Rigs are left/right symmetric with a **constant per-root index offset**
(`+25`, `+17`, `+12`), so naming one side localises its mirror.

## One rig decoded completely

Root `0x48dcbb01` is 34/34 named: per side one calf, `finger00`, four
three-segment finger chains (`finger11–13`, `21–23`, `31–33`, `41–43`), a foot, a
forearm and a hand — 17 bones per side, the right block starting 17 indices after
the left. Artifact: `handoff/script-skeleton-0x48dcbb01.tsv`.

## What is still closed

The table hashes split into two **disjoint** universes: 282 in the 13 ped/rig
roots (99 named, 35 %) and **330 in the other 31 roots**, which resist anatomy
words, vehicle `part_position` forms (`door_lf`), separators and numeric
patterns. Their nibble distributions are uniform, so they are name hashes whose
vocabulary is still unknown.

## Reproduce

```sh
python3 tools/bone_name_probe.py --no-corpus     # curated, zero collision risk
python3 tools/bone_name_probe.py                 # adds harvested words
```
