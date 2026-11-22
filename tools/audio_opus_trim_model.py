"""Test the AWC Opus trim model against the exported decode table.

The exported WAVs are untrimmed: `decoded_frames` is packets x frame size, and
`declared_samples` is the stream's true length counted across channels (mono:
per channel; stereo: both channels).  The difference is the total trim, which
the model splits into a fixed encoder pre-skip plus 0..one-packet end padding:

    pre_skip = 1920 frames (40 ms at 48 kHz)
    end_trim = decoded_frames - declared_samples / channels - pre_skip
    valid    = 0 <= end_trim <= 960   (one 20 ms Opus packet)

Reports how many streams satisfy the model and lists the exceptions with their
seek-table status, which is where the two known outliers come from.
"""

import argparse
import csv
from collections import Counter
from pathlib import Path

PRE_SKIP = 1920
PACKET = 960


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", type=Path, default=Path("handoff/audio-opus-decode.tsv"))
    parser.add_argument("--tsv", type=Path, default=Path("handoff/audio-opus-trim-model.tsv"))
    args = parser.parse_args()

    rows = []
    exceptions = []
    with args.table.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["error"]:
                continue
            decoded = int(row["decoded_frames"])
            declared = int(row["declared_samples"])
            channels = int(row["channels"])
            trim = decoded - declared / channels
            end_trim = trim - PRE_SKIP
            valid = 0 <= end_trim <= PACKET
            record = {
                "path": row["path"],
                "stream": row["stream"],
                "channels": channels,
                "source_rate": row["source_rate"],
                "decoded_frames": decoded,
                "declared_samples": declared,
                "total_trim": round(trim),
                "end_trim": round(end_trim),
                "seek": row["seek"],
                "valid": int(valid),
            }
            rows.append(record)
            if not valid:
                exceptions.append(record)

    total = len(rows)
    valid = sum(row["valid"] for row in rows)
    print(f"streams: {total}, model holds: {valid} ({valid / total:.2%})")
    print(f"pre-skip {PRE_SKIP} frames, end trim 0..{PACKET}")
    ends = sorted(row["end_trim"] for row in rows if row["valid"])
    print(f"end trim: min {ends[0]}, p25 {ends[len(ends)//4]}, "
          f"median {ends[len(ends)//2]}, p75 {ends[3*len(ends)//4]}, max {ends[-1]}")
    print(f"zero end trim: {sum(1 for value in ends if value == 0)} streams")
    print("\nexceptions:")
    for row in exceptions:
        print(f"  {row['path'].split('/')[-1]} stream {row['stream']} "
              f"ch={row['channels']} total_trim={row['total_trim']} "
              f"end_trim={row['end_trim']} seek={row['seek']}")
    print("\nexception seek status:", dict(Counter(row["seek"] for row in exceptions)))

    fields = ["path", "stream", "channels", "source_rate", "decoded_frames",
              "declared_samples", "total_trim", "end_trim", "seek", "valid"]
    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w") as out:
        out.write("\t".join(fields) + "\n")
        for row in rows:
            out.write("\t".join(str(row[field]) for field in fields) + "\n")
    print(f"wrote {args.tsv}")


if __name__ == "__main__":
    main()
