"""Check that the numbers the docs publish still match the committed artifacts.

Docs drift silently: a count changes in a tool, the page keeps the old number, and
the published site becomes wrong without any test failing. This derives a handful
of counts straight from `handoff/` and then requires each one to appear (formatted
with thousands separators) somewhere in `docs/` or `README.md`.

    python3 tools/claims_check.py
    python3 tools/claims_check.py --list
"""

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def rows(path):
    with path.open() as handle:
        return sum(1 for _ in handle) - 1


def typed_rows(path):
    total = 0
    curated = {}
    with path.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            total += 1
            kind = row.get("type")
            curated[kind] = curated.get(kind, 0) + 1
    return total, curated


def sections_indexed(path):
    total = indexed = 0
    with path.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            total += 1
            if row.get("index_hash"):
                indexed += 1
    return total, indexed


def collect():
    """(label, value) pairs that the docs are expected to state."""
    claims = []
    names = ROOT / "handoff/names.tsv"
    if names.is_file():
        claims.append(("registry names", rows(names)))
    typed = ROOT / "handoff/psin-rows.tsv"
    if typed.is_file():
        total, kinds = typed_rows(typed)
        claims.append(("typed PSIN rows", total))
        claims.append(("int rows", kinds.get("0x101", 0)))
        claims.append(("float rows", kinds.get("0x102", 0)))
        claims.append(("bool rows", kinds.get("0x104", 0)))
    sections = ROOT / "handoff/script-sections.tsv"
    if sections.is_file():
        total, indexed = sections_indexed(sections)
        claims.append(("sections", total))
        claims.append(("indexed sections", indexed))
    vocabulary = ROOT / "handoff/psin-vocabulary.tsv"
    if vocabulary.is_file():
        claims.append(("curated vocabulary rows", rows(vocabulary)))
    return claims


def docs_text():
    parts = []
    for path in list((ROOT / "docs").rglob("*.md")) + [ROOT / "README.md"]:
        parts.append(path.read_text())
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="print the derived values")
    args = parser.parse_args()

    claims = collect()
    if not claims:
        print("no artifacts present; nothing to check")
        return 0
    if args.list:
        for label, value in claims:
            print(f"{label:24s} {value:,}")
        return 0

    text = docs_text()
    missing = []
    for label, value in claims:
        formatted = f"{value:,}"
        if formatted not in text:
            missing.append((label, formatted))
    if missing:
        print("docs do not state:")
        for label, formatted in missing:
            print(f"  {label:24s} {formatted}")
        return 1
    print(f"all {len(claims)} published counts match the artifacts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
