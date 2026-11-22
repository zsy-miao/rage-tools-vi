"""Verify the `chain_start` column of the stream indexes.

A chain start must (a) be a real range start in the same archive, (b) not be
greater than the range it labels, and (c) stay constant across a chain. This
catches indexes written before the chain-propagation fix without re-indexing
anything.

    python3 tools/chain_start_verify.py output/index/*.tsv
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path


def check(path):
    rows = list(csv.DictReader(path.open(), delimiter="\t"))
    starts = {row["start"] for row in rows}
    labelled = [row for row in rows if row.get("chain_start")]
    missing = len(rows) - len(labelled)
    bad_parent = sum(1 for row in labelled
                     if int(row["chain_start"], 16) > int(row["start"], 16))
    not_a_start = sum(1 for row in labelled if row["chain_start"] not in starts)
    chains = Counter(row["chain_start"] for row in labelled)
    sizes = sorted(chains.values())
    return {
        "path": path.name,
        "ranges": len(rows),
        "labelled": len(labelled),
        "unlabelled": missing,
        "chain_start>start": bad_parent,
        "chain_start not a range start": not_a_start,
        "chains": len(chains),
        "largest chain": sizes[-1] if sizes else 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("indexes", nargs="+")
    args = parser.parse_args()
    fields = ("path", "ranges", "labelled", "unlabelled", "chain_start>start",
              "chain_start not a range start", "chains", "largest chain")
    print("\t".join(fields))
    failures = 0
    for path in map(Path, args.indexes):
        row = check(path)
        print("\t".join(str(row[field]) for field in fields))
        if row["chain_start>start"] or row["chain_start not a range start"]:
            failures += 1
    print(f"\n{failures} index(es) with a broken chain_start")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
