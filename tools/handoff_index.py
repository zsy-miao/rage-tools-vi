"""Regenerate `handoff/README.md`: what each artifact is and what makes it.

    python3 tools/handoff_index.py
"""
import csv
from pathlib import Path

PRODUCERS = [
    ("names.tsv, name-coverage.tsv", "tools/name_registry.py --build, tools/annotate_handoff.py"),
    ("psin-*.tsv", "tools/psin_extract.py, tools/psin_entries.py, tools/psin_segment.py"),
    ("bone-hash-names*.tsv, rig-names-corpus.tsv", "tools/bone_name_probe.py, tools/rig_name_corpus_probe.py"),
    ("weight-hash*.tsv", "tools/rig_name_corpus_probe.py"),
    ("pack-model-fit.tsv", "tools/pack_model_fit.py"),
    ("entry manifests (*-entries*.tsv)", "tools/pair_entry_manifest.py"),
    ("index and extents tables", "tools/stream_index.py, tools/pack_extents.py, tools/frontb_stride.py"),
    ("audio tables", "tools/awc_framing_ff02.py, tools/extract_awc_ff02.py"),
    ("header census", "tools/header_census.py"),
]


def main():
    lines = ["# handoff artifacts", "",
             "Verified data products: manifests, name tables and measurements.",
             "Every file is regenerable from the committed tools plus the source",
             "archives, which stay local. `tools/check.sh` verifies that the tools",
             "still agree with these files.", "",
             "| File | Rows | Columns |", "| --- | ---: | --- |"]
    for path in sorted(Path("handoff").glob("*.tsv")):
        with path.open() as handle:
            reader = csv.reader(handle, delimiter="\t")
            try:
                header = next(reader)
            except StopIteration:
                continue
            rows = sum(1 for _ in reader)
        columns = ", ".join(f"`{c}`" for c in header[:6])
        if len(header) > 6:
            columns += f", … ({len(header)} total)"
        lines.append(f"| `{path.name}` | {rows:,} | {columns} |")
    for path in sorted(Path("handoff").glob("*.md")):
        if path.name != "README.md":
            lines.append(f"| `{path.name}` | — | notes |")
    lines += ["", "## Producing tools", "", "| Product | Tool |", "| --- | --- |"]
    lines += [f"| {product} | `{tool}` |" for product, tool in PRODUCERS]
    lines.append("")
    Path("handoff/README.md").write_text("\n".join(lines))
    print(f"handoff/README.md: {len(list(Path('handoff').glob('*.tsv')))} tables")


if __name__ == "__main__":
    main()
