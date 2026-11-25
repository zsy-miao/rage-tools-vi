# Class-0 skeleton family names

## Done

Recomputed the core and union hash sets for all 16 families from the geometry
table and reproduced all recorded counts. The 44 roots use 612 unique bone
hashes. No root matched a pointer-backed model resource name or its stem. No
bone matched those names, stems, or the harvested PSIN name corpus.

## Artifacts

- `handoff/data-skeleton-family-links.tsv` reports the comparison per family.
- `tools/data_skeleton_family_links.py` reproduces it from the harvested names.

```sh
python3 tools/data_skeleton_family_links.py REPO_ROOT \
  output/data.rpf/resource-names.tsv > handoff/data-skeleton-family-links.tsv
```

## Needs

The resource list contains 2,502 named weapon models and components from the
child archive at `0x1228e000`. This test covers JOAAT of the full names and
stems, with original and lowercase spelling, and JOAAT of 3,212 PSIN names.
Family geometry alone cannot verify a model name, layout, or bone order.

## Next

Use a decoded model skeleton with an independent ordered bone table to test
the hash namespace and establish a mapping. F02 and F07 remain narrow-family
candidates. The dimensions of F03 and F04 make them larger-model candidates.
