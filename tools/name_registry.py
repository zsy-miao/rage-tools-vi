"""One name registry, and the two things anyone actually needs from it.

Every resolved hash in this repository lives in a file with its own schema:
`bone-hash-names.tsv`, `weight-hash-names.tsv`, `psin-names.tsv`, the candidate
tables. Nothing can join against that. This tool merges them into
`handoff/names.tsv` and exposes the registry three ways:

    # rebuild the registry
    python3 tools/name_registry.py --build

    # what is 0x01166164?
    python3 tools/name_registry.py --lookup 0x01166164

    # add a `name` column to any TSV that carries a hash column
    python3 tools/name_registry.py --annotate handoff/script-bones.tsv \\
        --column bone_hash --out handoff/script-bones-named.tsv

Confidence ordering is strict: `curated` beats `grammar`, which beats `corpus`,
which beats `candidate`. A hash resolves to the highest-confidence name, and the
losing names are kept in a `also_known_as` column rather than discarded.
"""

import argparse
import csv
import sys
from pathlib import Path

REGISTRY = Path("handoff/names.tsv")

# (path, hash column, name column, kind, confidence, filter)
SOURCES = [
    ("handoff/bone-hash-names-curated.tsv", "bone_hash", "name", "bone", "curated", None),
    ("handoff/bone-hash-names.tsv", "bone_hash", "name", "bone", "grammar", None),
    ("handoff/weight-hash-names.tsv", "weight_hash", "name", "weight", "curated", None),
    ("handoff/weight-hash-candidates.tsv", "weight_hash", "name", "weight", "candidate", None),
    ("handoff/rig-names-corpus.tsv", "hash", "name", "bone", "corpus", None),
    ("handoff/psin-names.tsv", "hash", "name", "property/key", "corpus", None),
    # rig families list every member root in one comma-separated column
    ("handoff/script-bone-template-families.tsv", "roots", "family_id", "rig", "corpus", None),
]

RANK = {"curated": 4, "meta": 3, "grammar": 2, "corpus": 1, "candidate": 0}

# Plain name lists, hashed rather than looked up. The engine's metadata table is
# exact case; the archive's identifier convention is lowercase, so both forms
# are registered.
NAME_LISTS = [("cache/vocab/codewalker-names.txt", "meta", "meta")]


def joaat(text):
    value = 0
    for byte in text.encode():
        value = (value + byte) & 0xFFFFFFFF
        value = (value + (value << 10)) & 0xFFFFFFFF
        value ^= value >> 6
    value = (value + (value << 3)) & 0xFFFFFFFF
    value ^= value >> 11
    value = (value + (value << 15)) & 0xFFFFFFFF
    return value


def build(path=REGISTRY):
    entries = {}
    for source, hash_column, name_column, kind, confidence, _ in SOURCES:
        handle = Path(source)
        if not handle.is_file():
            continue
        for row in csv.DictReader(handle.open(), delimiter="\t"):
            raw = (row.get(hash_column) or "").strip()
            name = (row.get(name_column) or "").strip()
            if not raw or not name:
                continue
            # Some tables list several hashes in one cell (rig family membership).
            for piece in raw.replace(";", ",").split(","):
                piece = piece.strip()
                if not piece.startswith("0x"):
                    continue
                value = int(piece, 16)
                entry = entries.setdefault(value, {"kind": kind, "best": None, "seen": []})
                entry["seen"].append((confidence, name, Path(source).name))
                if entry["best"] is None or RANK[confidence] > RANK[entry["best"][0]]:
                    entry["best"] = (confidence, name, Path(source).name)
    for source, kind, confidence in NAME_LISTS:
        handle = Path(source)
        if not handle.is_file():
            continue
        for line in handle.read_text(errors="ignore").splitlines():
            name = line.strip()
            if not name or name.startswith("#"):
                continue
            for form in {name, name.lower()}:
                value = joaat(form)
                entry = entries.setdefault(value, {"kind": kind, "best": None, "seen": []})
                entry["seen"].append((confidence, name, handle.name))
                if entry["best"] is None or RANK[confidence] > RANK[entry["best"][0]]:
                    entry["best"] = (confidence, name, handle.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as out:
        out.write("hash\tname\tkind\tconfidence\tsource\talso_known_as\tambiguous\n")
        for value in sorted(entries):
            entry = entries[value]
            confidence, name, source = entry["best"]
            spellings = {other.lower() for _, other, _ in entry["seen"]}
            others = sorted({other for _, other, _ in entry["seen"]
                             if other.lower() != name.lower()})
            # Two different real strings can share a 32-bit JOAAT. Say so instead
            # of presenting the higher-ranked one as the answer.
            ambiguous = 1 if len(spellings) > 1 else 0
            out.write(f"0x{value:08x}\t{name}\t{entry['kind']}\t{confidence}\t"
                      f"{source}\t{','.join(others)}\t{ambiguous}\n")
    counts = {}
    for entry in entries.values():
        counts[entry["best"][0]] = counts.get(entry["best"][0], 0) + 1
    ambiguous = sum(1 for entry in entries.values()
                    if len({other.lower() for _, other, _ in entry["seen"]}) > 1)
    print(f"registry: {len(entries)} names -> {path}")
    print("by confidence:", dict(sorted(counts.items(), key=lambda kv: -kv[1])))
    print(f"ambiguous (two real names, one JOAAT): {ambiguous}")
    return 0


def load(path=REGISTRY):
    if not path.is_file():
        raise SystemExit(f"{path} is missing; run --build first")
    return {int(row["hash"], 16): row
            for row in csv.DictReader(path.open(), delimiter="\t")}


def lookup(values, path=REGISTRY):
    table = load(path)
    found = 0
    for value in values:
        key = int(value, 0)
        row = table.get(key)
        if row:
            found += 1
            extra = f"  (also {row['also_known_as']})" if row["also_known_as"] else ""
            if row.get("ambiguous") == "1":
                extra += "  [ambiguous: JOAAT collision]"
            print(f"0x{key:08x}  {row['name']:32s} {row['kind']:12s} "
                  f"{row['confidence']:9s} {row['source']}{extra}")
        else:
            print(f"0x{key:08x}  <unresolved>")
    return 0 if found == len(values) else 1


def annotate(source, column, out, path=REGISTRY):
    table = load(path)
    rows = list(csv.DictReader(Path(source).open(), delimiter="\t"))
    if not rows:
        raise SystemExit(f"{source} is empty")
    if column not in rows[0]:
        raise SystemExit(f"{source} has no column {column!r}; "
                         f"columns are {', '.join(rows[0])}")
    fields = list(rows[0]) + ["name", "name_kind", "name_confidence"]
    resolved = 0
    for row in rows:
        raw = (row.get(column) or "").strip()
        hit = table.get(int(raw, 16)) if raw.startswith("0x") else None
        row["name"] = hit["name"] if hit else ""
        row["name_kind"] = hit["kind"] if hit else ""
        row["name_confidence"] = hit["confidence"] if hit else ""
        resolved += 1 if hit else 0
    with Path(out).open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t",
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"{out}: {resolved} of {len(rows)} rows named "
          f"({resolved / len(rows):.1%})")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--lookup", nargs="+", metavar="HASH")
    parser.add_argument("--annotate", metavar="TSV")
    parser.add_argument("--column", default="hash")
    parser.add_argument("--out", metavar="TSV")
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    args = parser.parse_args(argv)

    if args.build:
        return build(args.registry)
    if args.lookup:
        return lookup(args.lookup, args.registry)
    if args.annotate:
        if not args.out:
            parser.error("--annotate needs --out")
        return annotate(args.annotate, args.column, args.out, args.registry)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
