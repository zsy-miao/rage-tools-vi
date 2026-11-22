"""Measure Front A, Front B, and trailer byte statistics for every census header.

Encrypted metadata regions have byte entropy close to 8 and no zero runs.
Plaintext tables show repeated zero bytes, small integer fields, and printable
names.  This probe ranks headers by region entropy so the lowest-entropy packs
can be dumped and decoded first.

Inputs are the census TSV from `tools/header_census.py`.  Regions:
  Front A = 0x60 .. block            (variable, names/paths)
  Front B = block .. front_end        (fixed stride table: 9N or 10N)
  trailer = end - trailer_bytes .. end (end unknown for nested packs, so the
            trailer is measured from the parent file end unless --parent-ends
            is unavailable, in which case it is skipped)
"""

import argparse
import csv
import math
import random
import struct
from collections import Counter
from pathlib import Path

HEADER_SIZE = 0x60

def expected_random_entropy(n):
    """Expected plug-in byte entropy of n uniform random bytes."""
    if n >= 1000:
        return 8.0 - 255.0 / (2.0 * n * math.log(2.0))
    rng = random.Random(0x52504639)
    total = 0.0
    trials = 400
    for _ in range(trials):
        counts = Counter(rng.randbytes(n))
        total += -sum((c / n) * math.log2(c / n) for c in counts.values())
    return total / trials


def entropy(data):
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def stats(data):
    if not data:
        return {"entropy": 0.0, "zeros": 0.0, "printable": 0.0, "unique": 0}
    n = len(data)
    zeros = data.count(0) / n
    printable = sum(1 for b in data if 32 <= b < 127 or b in (9, 10, 13)) / n
    return {
        "entropy": entropy(data),
        "zeros": zeros,
        "printable": printable,
        "unique": len(set(data)),
    }


def resolve(source, name):
    direct = source / name
    if direct.is_file():
        return direct
    matches = [path for path in source.rglob(name) if path.is_file()]
    if len(matches) != 1:
        raise SystemExit(f"cannot resolve {name} under {source}")
    return matches[0]


def load(path):
    with path.open() as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = []
        for row in reader:
            row["offset"] = int(row["offset"], 0)
            for field in ("mode", "version", "count", "front_end", "block",
                          "size_b", "front_a", "trailer"):
                row[field] = int(row[field])
            rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, default=Path("handoff/header-census-full.tsv"))
    parser.add_argument("--source", type=Path,
                        default=Path("/run/media/lynxnathan/Mammoth/GTA6.Xbox.v1.0.2.1-CYBERLEEK"))
    parser.add_argument("--region", default="b", choices=("a", "b", "trailer"))
    parser.add_argument("--cap", type=int, default=1 << 20, help="bytes to sample per region")
    parser.add_argument("--threshold", type=float, default=7.9)
    parser.add_argument("--dump", type=int, default=0, help="hex-dump this many low-entropy regions")
    args = parser.parse_args()

    rows = load(args.census)
    handles = {}
    results = []
    for row in rows:
        name = row["archive"]
        if name not in handles:
            handles[name] = resolve(args.source, name).open("rb")
        handle = handles[name]
        started = row["offset"]
        if args.region == "a":
            begin, size = HEADER_SIZE, row["front_a"]
        elif args.region == "b":
            begin, size = row["block"], row["size_b"]
        else:
            # The pack end is unknown for nested packs, so the trailer can only
            # be measured for root packs, whose end is the file end.
            if started != 0:
                continue
            size = row["trailer"]
            handle.seek(0, 2)
            begin = handle.tell() - size
        if begin is None or begin < 0:
            continue
        size = min(size, args.cap)
        handle.seek(started + begin)
        data = handle.read(size)
        if len(data) != size:
            continue
        entry = stats(data)
        entry["expected"] = expected_random_entropy(size)
        entry["deficit"] = entry["expected"] - entry["entropy"]
        entry.update(
            archive=name,
            offset=started,
            mode=row["mode"],
            version=row["version"],
            count=row["count"],
            size=size,
        )
        results.append(entry)
    for handle in handles.values():
        handle.close()

    region = {"a": "front_a", "b": "size_b", "trailer": "trailer"}[args.region]
    print(f"region: {region}, rows measured: {len(results)}")
    hist = Counter(round(entry["entropy"]) for entry in results)
    print("entropy histogram:", dict(sorted(hist.items())))
    for field in ("entropy", "deficit", "zeros", "printable"):
        values = sorted(entry[field] for entry in results)
        n = len(values)
        print(f"{field:10s} min {values[0]:.3f} p25 {values[n//4]:.3f} "
              f"med {values[n//2]:.3f} p75 {values[3*n//4]:.3f} max {values[-1]:.3f}")

    listed = [entry for entry in results if entry["deficit"] > args.threshold]
    print(f"\nregions with entropy deficit > {args.threshold}: {len(listed)}")
    for entry in sorted(listed, key=lambda e: -e["deficit"])[:20]:
        print(f"  {entry['archive']:24s} 0x{entry['offset']:x} "
              f"mode 0x{entry['mode']:08x} N={entry['count']:<6} "
              f"bytes={entry['size']:<8} H={entry['entropy']:.3f}/{entry['expected']:.3f} "
              f"deficit={entry['deficit']:.3f} zeros={entry['zeros']:.3f} "
              f"printable={entry['printable']:.3f}")

    if args.dump:
        handles = {}
        for entry in sorted(listed, key=lambda e: -e["deficit"])[: args.dump]:
            name = entry["archive"]
            if name not in handles:
                handles[name] = resolve(args.source, name).open("rb")
            handle = handles[name]
            started = entry["offset"]
            if args.region == "a":
                begin = HEADER_SIZE
            elif args.region == "b":
                begin = entry["offset"]  # placeholder, recomputed below
            print(f"\n{name} @0x{started:x} mode 0x{entry['mode']:08x} N={entry['count']}")
            if args.region == "b":
                header = handle.seek(started)
                handle.seek(started)
                block = struct.unpack_from("<I", handle.read(0x10), 8)[0]
                begin = block
            handle.seek(started + begin)
            data = handle.read(min(entry["size"], 128))
            for at in range(0, len(data), 16):
                print(f"  +0x{at:04x} {data[at:at+16].hex(' ')}")
        for handle in handles.values():
            handle.close()


if __name__ == "__main__":
    main()
