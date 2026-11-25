"""Aggregate the AWC census tables into one result.

Inputs are the per-archive census written by `tools/extract_adat_gaps.py`:

    start  end  flags  streams  codecs  data_bytes  error

where `codecs` is `0xNN:count` pairs. This sums containers, streams, stream payload
bytes and per-codec counts per archive, and writes a single table so the totals are a
result rather than an arithmetic claim in prose.

    python3 tools/audio_census_totals.py handoff/audio-full-census.tsv \\
        handoff/audio-story000-census.tsv --out handoff/audio-census-totals.tsv
"""

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path


def codec_name(code) -> str:
    return {0x0B: "opus", 0x05: "xma2", 0x02: "ace1"}.get(code, f"0x{code:02x}")


def read_census(path):
    totals = Counter()
    codecs = Counter()
    flags = Counter()
    errors = Counter()
    with path.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            totals["containers"] += 1
            try:
                totals["streams"] += int(row["streams"])
                totals["data_bytes"] += int(row["data_bytes"])
            except (KeyError, ValueError):
                pass
            flags[row.get("flags", "")] += 1
            if row.get("error"):
                errors[row["error"]] += 1
            for piece in (row.get("codecs") or "").split(","):
                if not piece:
                    continue
                code, _, count = piece.partition(":")
                try:
                    codecs[int(code, 16)] += int(count)
                except ValueError:
                    continue
    return {"totals": totals, "codecs": codecs, "flags": flags, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("censuses", nargs="+", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    grand = Counter()
    grand_codecs = Counter()
    rows = []
    for path in args.censuses:
        if not path.is_file():
            print(f"missing {path}")
            continue
        result = read_census(path)
        name = path.stem.replace("-census", "").replace("audio-", "")
        rows.append((name, result))
        grand.update(result["totals"])
        grand_codecs.update(result["codecs"])

    print(f"{'archive':22s} {'containers':>11s} {'streams':>12s} {'data GB':>9s}")
    print("-" * 58)
    for name, result in rows:
        totals = result["totals"]
        print(f"{name:22s} {totals['containers']:11,d} {totals['streams']:12,d} "
              f"{totals['data_bytes'] / 1e9:9.2f}")
    print("-" * 58)
    print(f"{'total':22s} {grand['containers']:11,d} {grand['streams']:12,d} "
          f"{grand['data_bytes'] / 1e9:9.2f}")
    print("\ncodecs across the census:")
    for code, count in grand_codecs.most_common(8):
        print(f"  {codec_name(code):6s} {count:12,d}")
    for name, result in rows:
        if result["errors"]:
            detail = ", ".join(f"{k} x{v}" for k, v in result["errors"].most_common(3))
            print(f"  {name}: errors {detail}")
        if result["flags"]:
            detail = ", ".join(f"0x{k}={v}" for k, v in result["flags"].most_common(3))
            print(f"  {name}: flags {detail}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as handle:
            handle.write("archive\tcontainers\tstreams\tdata_bytes\tdata_gb\n")
            for name, result in rows:
                totals = result["totals"]
                handle.write(f"{name}\t{totals['containers']}\t{totals['streams']}\t"
                             f"{totals['data_bytes']}\t{totals['data_bytes'] / 1e9:.2f}\n")
            handle.write(f"total\t{grand['containers']}\t{grand['streams']}\t"
                         f"{grand['data_bytes']}\t{grand['data_bytes'] / 1e9:.2f}\n")
            handle.write("\ncodec\tstreams\n")
            for code, count in grand_codecs.most_common():
                handle.write(f"{codec_name(code)}\t{count}\n")
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
