"""Cipher battery for the masked RPF9 regions.

Runs the same tests on any set of ciphertext blobs and reports what each one
rules in or out:

  * plug-in byte entropy, against the maximum for the sample size;
  * duplicate blobs (deterministic encryption: equal plaintext, equal ciphertext);
  * same-length XOR entropy (a stream cipher with a fixed keystream would leak
    plaintext structure here);
  * repeating-key XOR sweep: mean entropy of `C[i] ^ C[i+p]` for small periods;
  * cipher-table presence in a binary list (AES S-box / Te0, ChaCha/Salsa sigma).

Usage: `python3 tools/crypt_battery.py --dir output/extracted/... --suffix .awc`
is meaningless for audio; this tool is aimed at the LSNS payloads and the script
blob, which the caller extracts first with `--lsns` or `--blob`.
"""

import argparse
import csv
import math
import struct
import zlib
from collections import Counter, defaultdict
from pathlib import Path

SIGS = {
    "AES S-box": bytes.fromhex("637c777bf26b6fc53001672bfed7ab76"),
    "AES Te0": bytes.fromhex("a56363c6"),
    "AES rcon": bytes.fromhex("0102040810204080"),
    "SHA-256 K": bytes.fromhex("428a2f98d728ae22"),
    "ChaCha sigma": b"expand 32-byte k",
    "Salsa sigma": b"expand 16-byte k",
}


def entropy(data):
    if not data:
        return 0.0
    counts = Counter(data)
    n = len(data)
    return -sum((count / n) * math.log2(count / n) for count in counts.values())


def sections(body):
    out = []
    offset = 0
    while offset + 8 <= len(body):
        tag = body[offset:offset + 4].decode("ascii", "ignore")
        size = struct.unpack_from(">I", body, offset + 4)[0]
        if not tag.isupper() or size < 8 or offset + size > len(body):
            break
        out.append((tag, offset, size))
        offset += size
    return out


def lsns_bodies(archive, index):
    """Return the encrypted LSNS payloads of every PSIN record in a pack."""
    rows = sorted((int(r["start"], 16), int(r["end"], 16))
                  for r in csv.DictReader(index.open(), delimiter="\t")
                  if r["kind"] == "zlib")
    data = archive.read_bytes()
    bodies = []
    position = 0
    while position < len(rows):
        start, end = rows[position]
        try:
            body = zlib.decompress(data[start:end])
        except zlib.error:
            position += 1
            continue
        if body.startswith(b"PSIN"):
            if len(body) == 65536 and position + 1 < len(rows):
                nxt_start, nxt_end = rows[position + 1]
                try:
                    body += zlib.decompress(data[nxt_start:nxt_end])
                except zlib.error:
                    pass
            for tag, offset, size in sections(body):
                if tag != "LSNS":
                    continue
                payload = body[offset + 8:offset + size]
                length = struct.unpack_from("<I", payload, 8)[0]
                bodies.append(payload[12:12 + length])
        position += 1
    return bodies


def report(blobs, label):
    print(f"\n=== {label}: {len(blobs)} blobs, {sum(len(b) for b in blobs):,} bytes")
    hs = [entropy(b) for b in blobs if b]
    if hs:
        print(f"  entropy: mean {sum(hs)/len(hs):.3f} min {min(hs):.3f} max {max(hs):.3f}")
    duplicates = Counter(blobs)
    groups = sorted(((count, len(blob)) for blob, count in duplicates.items() if count > 1),
                    reverse=True)
    print(f"  distinct: {len(duplicates)} of {len(blobs)}; duplicate groups "
          f"(copies, bytes): {groups[:4]}")
    by_length = defaultdict(list)
    for blob in blobs:
        by_length[len(blob)].append(blob)
    print("  length classes:", sorted(((length, len(group)) for length, group in by_length.items()),
                                      key=lambda item: -item[1])[:5])
    same = [group for group in by_length.values() if len(group) > 1]
    if same:
        ranges = []
        for group in same:
            for left in range(min(3, len(group))):
                for right in range(left + 1, min(3, len(group))):
                    x = bytes(a ^ b for a, b in zip(group[left], group[right]))
                    ranges.append(entropy(x))
        print(f"  same-length XOR entropy: mean {sum(ranges)/len(ranges):.4f} "
              f"min {min(ranges):.4f} max {max(ranges):.4f}")
    sample = [blob for blob in blobs if len(blob) >= 512][:120]
    if sample:
        sweep = {}
        for period in range(1, 25):
            values = [entropy(bytes(blob[i] ^ blob[i + period]
                                    for i in range(len(blob) - period)))
                      for blob in sample]
            sweep[period] = sum(values) / len(values)
        low = sorted(sweep.items(), key=lambda item: item[1])[:3]
        print(f"  repeating-key sweep: min {low[0][1]:.4f} at p={low[0][0]}, "
              f"max {max(sweep.values()):.4f}")
    first = defaultdict(set)
    for blob in blobs:
        if len(blob) >= 16:
            first[len(blob)].add(blob[:16])
    print(f"  first block unique per length: "
          f"{sum(1 for v in first.values() if len(v) == 1)}/{len(first)} lengths")


def scan_binaries(paths):
    print("\n=== cipher tables in binaries")
    for path in paths:
        if not path.is_file():
            continue
        data = path.read_bytes()
        hits = [name for name, sig in SIGS.items() if data.find(sig) >= 0]
        print(f"  {path.name:32s} {len(data):>12,}  {hits}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("script.rpf"))
    parser.add_argument("--index", type=Path, default=Path("output/index/script.tsv"))
    parser.add_argument("--binaries", nargs="*", type=Path, default=[])
    parser.add_argument("--blob", nargs=2, type=lambda value: int(value, 0),
                        help="raw blob start and end in the archive, e.g. 0x2010 0x52fe0")
    args = parser.parse_args()

    report(lsns_bodies(args.archive, args.index), "LSNS bodies")
    if args.blob:
        start, end = args.blob
        data = args.archive.read_bytes()[start:end]
        report([data], f"raw blob 0x{start:x}..0x{end:x}")
    if args.binaries:
        scan_binaries(args.binaries)


if __name__ == "__main__":
    main()
