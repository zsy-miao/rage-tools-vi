"""Compare the first and last ciphertext blocks of Front B across the census.

A deterministic cipher with a fixed chaining value repeats the first 16-byte
block whenever the first plaintext block repeats.  Identical first blocks
across unrelated packs therefore identify a fixed plaintext prefix, and the
mapping onto the +0x50 header block tests whether that block selects the key.
"""

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

HEADER_SIZE = 0x60


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
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()

    rows = load(args.census)
    handles = {}
    firsts = defaultdict(list)
    lasts = defaultdict(list)
    keys = defaultdict(list)
    for row in rows:
        name = row["archive"]
        if name not in handles:
            handles[name] = resolve(args.source, name).open("rb")
        handle = handles[name]
        started = row["offset"]
        handle.seek(started)
        header = handle.read(HEADER_SIZE)
        key = bytes(header[0x50:0x60]).hex()
        row["key"] = key
        if row["size_b"] < 16:
            continue
        handle.seek(started + row["block"])
        first = handle.read(16).hex()
        handle.seek(started + row["front_end"] - 16)
        last = handle.read(16).hex()
        firsts[first].append(row)
        lasts[last].append(row)
        keys[key].append(row)
    for handle in handles.values():
        handle.close()

    print(f"headers: {len(rows)}")
    print(f"distinct Front B first blocks: {len(firsts)}")
    print(f"distinct Front B last blocks:  {len(lasts)}")
    print(f"distinct +0x50 blocks:         {len(keys)}")

    for label, groups in (("first", firsts), ("last", lasts)):
        repeated = {value: group for value, group in groups.items() if len(group) > 1}
        print(f"\nrepeated {label} blocks: {len(repeated)} values, "
              f"{sum(len(g) for g in repeated.values())} headers")
        for value, group in sorted(repeated.items(), key=lambda item: -len(item[1]))[: args.limit]:
            modes = Counter(f"0x{row['mode']:08x}/0x{row['version']:08x}" for row in group)
            counts = Counter(row["count"] for row in group)
            archives = sorted({row["archive"] for row in group})
            print(f"  {len(group):4d} {value}")
            print(f"       modes {dict(modes.most_common(3))}")
            print(f"       N values {sorted(counts)[:8]}")
            print(f"       files {archives[:6]}")

    print("\n+0x50 key block versus mode family")
    for key, group in sorted(keys.items(), key=lambda item: -len(item[1])):
        families = Counter(row["mode"] >> 16 for row in group)
        versions = Counter(row["version"] for row in group)
        firsts_here = {value for value, rows_ in firsts.items() for row in rows_ if row["key"] == key}
        print(f"  {key}  headers {len(group):4d}  families {dict(sorted(families.items()))}  "
              f"versions {[f'0x{v:08x}' for v in versions]}  distinct firsts {len(firsts_here)}")


if __name__ == "__main__":
    main()
