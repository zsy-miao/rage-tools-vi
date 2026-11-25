"""Which entry model does each archive follow, and how well does it fit?

The manifests in `handoff/` were built per archive with a hand-picked unit
(pairs for `core_bvh4` and `textures`, chains for `data` and `navmeshes`). This
tool replaces the guess with a measurement: for each archive compare the declared
entry count with the number of zlib streams and with how many of those streams
are exactly 65,536 bytes decoded (the only ones that can continue a chain).

    python3 tools/entry_model.py

Output columns:

    ratio      streams / declared — 2.0 suggests struct+data pairs, ~1.0 single
               streams, between 1 and 2 a chain model
    cont_need  streams - declared, i.e. how many continuations must exist
    cont_64k   streams that decode to exactly 65,536 bytes
    cover      cont_64k / cont_need — how much of the chain model the page rule
               explains
"""
import argparse
import csv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reconciliation", type=Path,
                        default=Path("handoff/entry-reconciliation.tsv"))
    parser.add_argument("--index", type=Path, default=Path("output/index"))
    args = parser.parse_args()

    print(f"{'archive':28s} {'declared':>9} {'streams':>8} {'ratio':>6} "
          f"{'cont_need':>9} {'cont_64k':>8} {'cover':>6}  model")
    for row in sorted(csv.DictReader(args.reconciliation.open(), delimiter="\t"),
                      key=lambda r: r["archive"]):
        index = args.index / f"{row['archive'][:-4]}.tsv"
        if not index.is_file():
            continue
        streams = [r for r in csv.DictReader(index.open(), delimiter="\t")
                   if r["kind"] == "zlib"]
        declared = int(row["declared"])
        if declared <= 0 or not streams:
            continue
        total = len(streams)
        ratio = total / declared
        need = total - declared
        full = sum(1 for r in streams if int(r["decoded_bytes"] or 0) == 65536)
        cover = full / need if need > 0 else 0.0
        if abs(ratio - 2) < 0.15:
            model = "pairs"
        elif abs(ratio - 1) < 0.05:
            model = "single"
        elif need > 0 and cover > 0.9:
            model = "pages"
        else:
            model = "mixed"
        print(f"{row['archive']:28s} {declared:>9} {total:>8} {ratio:>6.2f} "
              f"{need:>9} {full:>8} {cover:>6.0%}  {model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
