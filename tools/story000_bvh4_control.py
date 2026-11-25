#!/usr/bin/env python3
"""Build the four-range XML control table for story000_bvh4.rpf."""
import argparse
import csv
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("handoff/story000-bvh4-control.tsv"))
    args = ap.parse_args()

    rows = []
    with args.manifest.open(newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            payload = Path(row["path"]).read_bytes()
            actual = hashlib.sha256(payload).hexdigest()
            if actual != row["sha256"] or len(payload) != int(row["decoded_bytes"]):
                raise ValueError(f"payload mismatch: {row['path']}")
            root = ET.fromstring(payload)
            xml_id = (root.findtext("id") or "").strip()
            rows.append({
                "start": row["start"],
                "end": row["end"],
                "stored_bytes": row["stored_bytes"],
                "decoded_bytes": row["decoded_bytes"],
                "sha256": row["sha256"],
                "xml_root": root.tag,
                "xml_id": xml_id,
                "payload": row["path"],
            })
    rows.sort(key=lambda item: int(item["start"], 16))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t",
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {args.out}: {len(rows)} XML ranges")


if __name__ == "__main__":
    main()
