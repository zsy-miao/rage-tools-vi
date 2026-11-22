# Skeleton-family namespace check

Bus handoff #0157, 2026-11-21. The existing tables support a relationship
between two pairs of F05 and F06 roots. The model and part names remain
unresolved.

## Tested namespaces

The probe rebuilt the 16 families from `script-bones.tsv` and
`script-bone-geometry.tsv` using the existing 0.75 Jaccard threshold. The
geometry table agrees on all 3,043 ordered bone rows. The exact-set template
table agrees on set membership for all 44 roots. F02 has six exact sets and
eight ordered templates, so matching an unordered hash set can leave the bone
order ambiguous.

The independent name input was the vehicle mover table. Its 233 model
names and six distinct named curve keys all reproduce their recorded 32-bit
JOAAT values under the standard zero initial state. The probe compared the
44 class-0 root IDs and 612 distinct bone hash words with the available model
and part hashes, including byte-swapped forms where shown:

| Compared words | Candidate namespace | Matches |
| --- | --- | ---: |
| 44 root IDs | 233 named vehicle model hashes, direct and byte-swapped | 0 |
| 612 bone hashes | 233 named vehicle model hashes, direct and byte-swapped | 0 |
| 612 bone hashes | 36 vehicle mover key hashes, direct and byte-swapped | 0 |
| 612 bone hashes | JOAAT of the four known window mover names without `_mover` | 0 |

## Consecutive-suffix ambiguity

Each JOAAT round can be inverted for a fixed string. The probe recovered the
32-bit initial state implied by every class-0 root and known vehicle name.
It retained states predicting at least two distinct names and root IDs. The
same procedure found no shared state for the six named mover keys against
the 612 bone words.

| Initial state | F05 root and available spelling | F06 root and available spelling |
| --- | --- | --- |
| `0x1090e2a8` | `0x96f3700e` as `gauntlet4` | `0x89a5d573` as `gauntlet5` |
| `0xc15af2d4` | `0x96f3700e` as `impaler5` | `0x89a5d573` as `impaler6` |
| `0xa36d0010` | `0xb4e9e8ce` as `gauntlet4` | `0x8fb71e69` as `gauntlet5` |
| `0x4f822e0b` | `0xb4e9e8ce` as `impaler5` | `0x8fb71e69` as `impaler6` |

Every hit uses a single shared stem and consecutive final digits. Undoing the
last round and subtracting the final byte recovers the same state for either
member of that pair. Changing the stem changes the seed and leaves the pair
fit intact. None of the four seeds predicts another root with a different
model stem from the same set of 233 controls. The repeated F05-to-F06 pairing
is a structural lead. Assigning either vehicle model requires an independent
decoded root/model reference or an ordered skeleton with named parts. The
allowed inputs have no paired ped, weapon, or prop skeletons.

## Reproduce

```sh
python3 -B tools/script_bone_namespace_probe.py > handoff/script-bone-namespace-probe.tsv
```

The TSV contains per-family direct match counts and template counts. The
terminal output lists the JOAAT controls and all repeated seed pairs.
