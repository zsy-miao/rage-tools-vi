#!/usr/bin/env python3
"""Extract locally mapped RPF9 ranges, with a manifest covering every stored byte."""

import argparse
import csv
from hashlib import sha256
import mmap
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zlib


def read_report(cli, command, archive):
    report = subprocess.check_output([cli.resolve(), command, archive], text=True)
    return list(csv.DictReader(report.splitlines(), delimiter="\t"))


def classify(data):
    if data.lstrip().startswith(b"<") or data.startswith(b"\xef\xbb\xbf"):
        try:
            root = ET.fromstring(data)
        except (ET.ParseError, ValueError, LookupError):
            pass
        else:
            return "xml", root.tag
    for magic in (b"PSIN", b"HMAP", b"SPS1", b"MHUI", b"RSC8", b"RSC9", b"TABL",
                  b"RIFF", b"OggS", b"DDS ", b"\x89PNG", b"9FPR"):
        if data.startswith(magic):
            return "bin", repr(magic)
    return "bin", ""


def flush_chain(directory, segments, decoded):
    extension, label = classify(decoded)
    path = f"decoded/{int(segments[0]['start'], 16):08x}.{extension}"
    (directory / path).write_bytes(decoded)
    offset = 0
    for row in segments:
        length = int(row["decoded_bytes"])
        row.update(file=path, file_offset=str(offset), format_hint=label if not offset else "")
        offset += length


def extract_ranges(data, directory, rows):
    (directory / "decoded").mkdir()
    (directory / "raw").mkdir()
    cursor = 0
    segments = []
    decoded = bytearray()
    active_chain = None
    for row in rows:
        start, end = (int(row[field], 16) for field in ("start", "end"))
        kind = row["kind"]
        if start != cursor or not start < end <= len(data) or end - start != int(row["stored_bytes"]):
            raise ValueError(f"map breaks byte coverage at {cursor:#x}")
        cursor = end
        stored = data[start:end]
        row["stored_sha256"] = sha256(stored).hexdigest()
        if kind == "zlib":
            if row["chain_start"] != active_chain:
                if segments:
                    flush_chain(directory, segments, decoded)
                segments = []
                decoded.clear()
                active_chain = row["chain_start"]
            decoder = zlib.decompressobj()
            chunk = decoder.decompress(stored)
            if not decoder.eof or decoder.unused_data or len(chunk) != int(row["decoded_bytes"]):
                raise ValueError(f"zlib size or stream boundary mismatch at {start:#x}")
            row["decoded_sha256"] = sha256(chunk).hexdigest()
            segments.append(row)
            decoded.extend(chunk)
        elif kind == "zero_run":
            if stored.count(0) != len(stored):
                raise ValueError(f"nonzero bytes in zero run at {start:#x}")
        elif kind in {"front", "trailer", "unclassified"}:
            path = f"raw/{start:08x}-{end:08x}.{kind}.bin"
            (directory / path).write_bytes(stored)
            row.update(file=path, file_offset="0")
        else:
            raise ValueError(f"unknown map kind {kind}")
    if segments:
        flush_chain(directory, segments, decoded)
    if cursor != len(data):
        raise ValueError(f"map ends early at {cursor:#x}")


def write_report(path, rows, fields):
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def extract_archive(cli, archive, output):
    destination = output / archive.name
    if destination.exists():
        raise FileExistsError(f"extraction already exists at {destination}")
    rows = read_report(cli, "map", archive)
    packs = read_report(cli, "packs", archive)
    with tempfile.TemporaryDirectory(prefix=f".{archive.name}-", dir=output) as temporary:
        stage = Path(temporary) / archive.name
        stage.mkdir()
        with archive.open("rb") as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as data:
            extract_ranges(data, stage, rows)
        write_report(stage / "ranges.tsv", rows, [
            *list(rows[0])[:6], "stored_sha256", "decoded_sha256", "file", "file_offset", "format_hint",
        ])
        write_report(stage / "packs.tsv", packs, list(packs[0]))
        stage.rename(destination)
    print(
        archive.name, len(packs), sum(row["kind"] == "zlib" for row in rows),
        len({row["chain_start"] for row in rows if row["kind"] == "zlib"}),
        sum(row["kind"] in {"front", "trailer", "unclassified"} for row in rows),
        sum(int(row["decoded_bytes"] or 0) for row in rows),
        sep="\t", flush=True,
    )


def verify_archive(archive, directory):
    with (directory / "ranges.tsv").open(newline="") as report:
        rows = list(csv.DictReader(report, delimiter="\t"))
    cursor = 0
    file_ends = {}
    with archive.open("rb") as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
        for row in rows:
            start, end = (int(row[field], 16) for field in ("start", "end"))
            if start != cursor or not start < end <= len(data) or end - start != int(row["stored_bytes"]):
                raise ValueError(f"manifest breaks byte coverage at {cursor:#x}")
            cursor = end
            stored = data[start:end]
            if sha256(stored).hexdigest() != row["stored_sha256"]:
                raise ValueError(f"source hash differs at {start:#x}")
            if row["kind"] == "zero_run":
                if stored.count(0) != len(stored):
                    raise ValueError(f"nonzero bytes in zero run at {start:#x}")
                continue
            file = directory / row["file"]
            offset = int(row["file_offset"])
            size = int(row["decoded_bytes"] or row["stored_bytes"])
            if offset != file_ends.get(file, 0):
                raise ValueError(f"output manifest breaks file coverage at {file}")
            with file.open("rb") as extracted:
                extracted.seek(offset)
                segment = extracted.read(size)
            expected_hash = row["decoded_sha256"] or row["stored_sha256"]
            if len(segment) != size or sha256(segment).hexdigest() != expected_hash:
                raise ValueError(f"output hash differs at {file}+{offset:#x}")
            file_ends[file] = offset + size
        if cursor != len(data):
            raise ValueError(f"manifest ends early at {cursor:#x}")
    if any(file.stat().st_size != end for file, end in file_ends.items()):
        raise ValueError(f"trailing unreported output in {directory}")
    print(archive.name, cursor, len(file_ends), sep="\t", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="directory of .rpf files or a single .rpf file")
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--cli", type=Path, default=Path("target/release/rage-tools-vi"))
    parser.add_argument("--verify", action="store_true", help="verify existing source and output hashes")
    args = parser.parse_args()
    archives = sorted(args.source.glob("*.rpf")) if args.source.is_dir() else [args.source]
    if not archives:
        parser.error("source contains no .rpf files")
    if args.verify:
        print("archive\tverified_stored_bytes\tverified_files", flush=True)
        for archive in archives:
            verify_archive(archive, args.output / archive.name)
    else:
        args.output.mkdir(parents=True, exist_ok=True)
        print("archive\theaders\tstreams\tchains\traw_files\tdecoded_bytes", flush=True)
        for archive in archives:
            extract_archive(args.cli, archive, args.output)


if __name__ == "__main__":
    main()
