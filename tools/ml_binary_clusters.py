#!/usr/bin/env python3
"""Cluster packs binary streams from byte-level features (proposal engine only)."""
import argparse
import csv
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.cluster import MiniBatchKMeans
from sklearn.preprocessing import StandardScaler


def features(path, size):
    raw = Path(path).read_bytes()[:4096]
    offset = 0
    while offset < len(raw) and raw[offset] == 0:
        offset += 1
    data = raw[offset:]
    n = len(data)
    counts = np.bincount(np.frombuffer(data, dtype=np.uint8), minlength=256).astype(np.float64)
    hist = counts.reshape(16, 16).sum(axis=1)
    hist /= max(n, 1)
    entropy = -sum((c / n) * math.log2(c / n) for c in counts if c) if n else 0.0
    zeros = data.count(0) / max(n, 1)
    printable = sum(1 for b in data if 32 <= b < 127 or b in (9, 10, 13)) / max(n, 1)
    u16 = np.frombuffer(data[: n // 2 * 2], dtype="<u2").astype(np.float64)
    u32 = np.frombuffer(data[: n // 4 * 4], dtype="<u4").astype(np.float64)
    u16_zero = float((u16 == 0).mean()) if len(u16) else 0.0
    u32_zero = float((u32 == 0).mean()) if len(u32) else 0.0
    u16_mean = float(u16.mean() / 65535) if len(u16) else 0.0
    u16_std = float(u16.std() / 65535) if len(u16) else 0.0
    u32_std = float(np.log1p(u32.std()) / 32) if len(u32) else 0.0
    head = np.zeros(16, dtype=np.float64)
    for i, b in enumerate(data[:16]):
        head[i] = b / 255.0
    bigrams = np.zeros(16, dtype=np.float64)
    for i in range(max(0, min(n - 1, 2048))):
        bigrams[(data[i] * 31 + data[i + 1]) & 15] += 1
    bigrams /= max(bigrams.sum(), 1)
    return np.concatenate([
        [math.log1p(size), math.log1p(offset), entropy, zeros, printable, u16_zero,
         u16_mean, u16_std, u32_zero, u32_std],
        hist, head, bigrams,
    ]).astype(np.float32)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("details", type=Path, nargs="?", default=Path("output/packs-signatures.tsv"))
    parser.add_argument("--clusters", type=int, default=32)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--details-out", type=Path, default=Path("output/packs-binary-clusters.tsv"))
    parser.add_argument("--summary", type=Path, default=Path("handoff/packs-binary-clusters.tsv"))
    args = parser.parse_args()

    rows = []
    with args.details.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["kind"] == "binary":
                rows.append(row)
                if args.limit and len(rows) >= args.limit:
                    break
    print("binary rows", len(rows))
    matrix = np.vstack([features(row["path"], int(row["decoded_bytes"])) for row in rows])
    matrix = StandardScaler().fit_transform(matrix)
    model = MiniBatchKMeans(
        n_clusters=args.clusters, batch_size=4096, random_state=1, n_init=3
    ).fit(matrix)
    labels = model.labels_

    clusters = defaultdict(list)
    for row, label in zip(rows, labels):
        clusters[int(label)].append(row)
    args.details_out.parent.mkdir(parents=True, exist_ok=True)
    with args.details_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["cluster", "start", "decoded_bytes", "head_hex", "path"])
        for row, label in zip(rows, labels):
            writer.writerow([int(label), row["start"], row["decoded_bytes"], row["head_hex"], row["path"]])

    summary = []
    for label, items in clusters.items():
        heads = Counter()
        for row in items:
            raw = Path(row["path"]).read_bytes()[:64]
            offset = 0
            while offset < len(raw) and raw[offset] == 0:
                offset += 1
            heads[raw[offset:offset + 8].hex()] += 1
        sizes = [int(row["decoded_bytes"]) for row in items]
        summary.append((
            label, len(items), int(sum(sizes) / len(sizes)), min(sizes), max(sizes),
            heads.most_common(1)[0][0], heads.most_common(1)[0][1],
            items[0]["path"],
        ))
    summary.sort(key=lambda row: -row[1])
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    with args.summary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["cluster", "streams", "avg_bytes", "min_bytes", "max_bytes", "top_head", "top_head_count", "sample"])
        writer.writerows(summary)
    print("cluster\tstreams\tavg_bytes\tmin\tmax\ttop_head\tsample")
    for row in summary:
        print(f"{row[0]}\t{row[1]}\t{row[2]}\t{row[3]}\t{row[4]}\t{row[5]}\t{row[7]}")


if __name__ == "__main__":
    main()
