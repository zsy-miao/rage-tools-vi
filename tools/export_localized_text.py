#!/usr/bin/env python3
"""Export readable strings from the identified data.rpf localization archives."""

import argparse
from collections import Counter
import csv
from pathlib import Path
import re


NULL_STRING = re.compile(rb"[^\0]+\0")
TEXT_RESOURCE_TAG = b"0DRPz"


def text_runs(data):
    """Yield contiguous runs of UTF-8 strings, with their decoded byte offsets."""
    run = []
    previous_end = 0
    for match in NULL_STRING.finditer(data):
        if match.start() != previous_end:
            if credible(run):
                yield from run
            run = []
        previous_end = match.end()
        value = decode_text(match.group()[:-1])
        if value is None:
            if credible(run):
                yield from run
            run = []
        else:
            run.append((match.start(), value))
    if credible(run):
        yield from run


def decode_text(raw):
    try:
        value = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not all(char.isprintable() or char in "\r\n\t" for char in value):
        return None
    if not any(char.isalnum() for char in value):
        return None
    return value


def credible(run):
    # A sequence of neighbors with natural text is stronger evidence than a
    # printable fragment from a pointer table or an incidental binary string.
    return len(run) >= 3 and sum(
        sum(char.isalpha() for char in value) >= 8 for _, value in run
    ) >= 2


def export(directory):
    counts = Counter()
    with (directory / "localized/groups.tsv").open(newline="") as groups, (
        directory / "localized/text.tsv"
    ).open("w", encoding="utf-8", newline="") as index:
        columns = ["archive", "stored_start", "stored_end", "binary_file", "text_file", "strings"]
        writer = csv.DictWriter(index, columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in csv.DictReader(groups, delimiter="\t"):
            archive = f"{row['language']}_final.rpf"
            output = directory / archive
            output.mkdir(exist_ok=True)
            source = directory / row["file"]
            with source.open("rb") as resource:
                header = resource.read(0x15)
                if header[0x10:] != TEXT_RESOURCE_TAG:
                    continue
                data = header + resource.read()
            counts["recognized"] += 1
            strings = list(text_runs(data))
            if not strings:
                continue
            path = output / f"{int(row['stored_start'], 16):06x}.txt"
            with path.open("w", encoding="utf-8", newline="\n") as text:
                for _, value in strings:
                    text.write(value)
                    text.write("\n")
            writer.writerow({
                "archive": archive, "stored_start": row["stored_start"], "stored_end": row["stored_end"],
                "binary_file": row["file"], "text_file": str(path.relative_to(directory)),
                "strings": len(strings),
            })
            counts["files"] += 1
            counts["strings"] += len(strings)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="?", default=Path("output/data.rpf"))
    args = parser.parse_args()
    counts = export(args.directory)
    print(f"{counts['files']} text files from {counts['recognized']} resources with the text tag, "
          f"{counts['strings']} string occurrences")


if __name__ == "__main__":
    main()
