#!/usr/bin/env python3
"""Report file(1) signatures for every regular file in a local extraction."""

import argparse
from collections import Counter
import csv
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = args.directory.resolve()
    if not root.is_dir():
        parser.error("expected an extraction directory")
    report = args.report.resolve()
    paths = sorted(
        path for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and path != report
    )
    if not paths or any("\n" in str(path) or "\r" in str(path) for path in paths):
        parser.error("expected files with no newline characters in their paths")
    scan = subprocess.run(
        ["file", "--brief", "--files-from", "-"],
        input="".join(f"{path}\n" for path in paths),
        capture_output=True,
        check=True,
        text=True,
    )
    descriptions = scan.stdout.splitlines()
    if scan.stderr or len(descriptions) != len(paths) or any(
        result.startswith(("ERROR:", "cannot open")) for result in descriptions
    ):
        raise RuntimeError(f"file(1) did not produce one result per path: {scan.stderr}")
    with report.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(["file", "bytes", "libmagic"])
        for path, description in zip(paths, descriptions, strict=True):
            writer.writerow([path.relative_to(root).as_posix(), path.stat().st_size, description])
    print(f"{len(paths):,} files scanned")
    for description, count in Counter(descriptions).most_common(15):
        print(count, description, sep="\t")


if __name__ == "__main__":
    main()
