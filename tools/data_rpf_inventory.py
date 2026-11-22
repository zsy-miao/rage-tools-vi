#!/usr/bin/env python3
"""Audit data.rpf pack bounds, PSIN records, and localized resource payloads."""

import argparse
from bisect import bisect_left
from collections import defaultdict
import csv
from dataclasses import dataclass
from hashlib import sha256
import mmap
from pathlib import Path
import re
import struct
import xml.etree.ElementTree as ET


PAGE_SIZE = 0x1000
SECTION_TAGS = (b"PSIN", b"LSCH", b"LENM", b"LSNS", b"LGID", b"LRSC", b"CHKS")
PSIN_SECTION_LAYOUTS = {
    SECTION_TAGS,
    (b"PSIN", b"PMAP", b"PSCH", b"PSIG", b"STNS", b"CHKS"),
    (b"PSIN", b"PMAP", b"PSCH", b"PSIG", b"STDN", b"STNS", b"CHKS"),
    (b"PSIN", b"PMAP", b"PSCH", b"PSIG", b"STFN", b"STNS", b"CHKS"),
}
RESOURCE_SUFFIX = re.compile(rb"\.#[a-z0-9]{2,5}\x00")
RESOURCE_NAME = re.compile(rb"[a-z][a-z0-9_]{2,126}")
# Translations of the same line about a hotel in the first resource.
LANGUAGE_MARKERS = {
    "american": "That's the hotel over there.",
    "brazilian": "É aquele hotel ali.",
    "chinesesimp": "那边是酒店",
    "chinesetrad": "就是那邊那間旅館",
    "french": "C'est cet hôtel-là.",
    "german": "Das da drüben ist das Hotel.",
    "italian": "è quello lì, l'hotel.",
    "japanese": "あれが例のホテル",
    "korean": "저기 있는 호텔 말이야.",
    "mexican": "Ese de ahí es el hotel.",
    "polish": "Tam jest hotel.",
    "russian": "Вон про тот отель",
    "spanish": "Ese es el hotel.",
}


def read_table(path):
    with path.open(newline="") as source:
        return list(csv.DictReader(source, delimiter="\t"))


@dataclass
class Span:
    start: int
    end: int
    kind: str
    path: str
    file_offset: int
    decoded_bytes: int
    stored_hash: str

    @classmethod
    def from_row(cls, row):
        return cls(
            int(row["start"], 16), int(row["end"], 16), row["kind"], row["file"],
            int(row["file_offset"] or 0), int(row["decoded_bytes"] or 0), row["stored_sha256"],
        )


@dataclass
class Trailer:
    start: int
    end: int
    stored_hash: str
    detection: str


def trailer_candidates(directory, spans, size):
    for span in spans:
        if span.kind != "unclassified" or span.end % 16 or span.end - span.start < size:
            continue
        start = span.end - size
        if start == span.start:
            yield Trailer(start, span.end, span.stored_hash, "exact_opaque_span")
            continue
        # The range mapper can fold a short pad into one opaque span.
        with (directory / span.path).open("rb") as source:
            source.seek(start - span.start - 1)
            if source.read(1) != b"\0":
                continue
            trailer = source.read(size)
            if len(trailer) == size and trailer[:1] != b"\0":
                yield Trailer(start, span.end, sha256(trailer).hexdigest(), "zero_delimited_suffix")


def psin_valid(data):
    cursor = 0
    tags = []
    while cursor < len(data) and len(tags) < len(SECTION_TAGS):
        if cursor + 8 > len(data):
            return False
        tag, size = struct.unpack_from(">4sI", data, cursor)
        if not 8 <= size <= len(data) - cursor:
            return False
        tags.append(tag)
        if tag == b"CHKS":
            if size < 12 or struct.unpack_from(">I", data, cursor + 8)[0] != len(data):
                return False
        cursor += size
    return cursor == len(data) and tuple(tags) in PSIN_SECTION_LAYOUTS


def stream_groups(streams):
    """Join neighboring streams across only the minimum padding to 16 bytes."""
    groups = []
    for span in streams:
        if groups and span.start == ((groups[-1][-1].end + 15) & ~15):
            groups[-1].append(span)
        else:
            groups.append([span])
    return groups


def read_streams(directory, group):
    result = bytearray()
    for span in group:
        with (directory / span.path).open("rb") as source:
            source.seek(span.file_offset)
            chunk = source.read(span.decoded_bytes)
        if len(chunk) != span.decoded_bytes:
            raise ValueError(f"short extracted stream at {span.start:#x}")
        result.extend(chunk)
    return result


def survey_packs(directory, spans):
    headers = read_table(directory / "packs.tsv")
    offsets = [int(row["header_offset"], 16) for row in headers]
    starts = [span.start for span in spans]
    scopes = []
    families = defaultdict(list)
    for index, header in enumerate(headers[1:], 1):
        start = offsets[index]
        front_end = int(header["front_end"], 16)
        limit = offsets[index + 1] if index + 1 < len(offsets) else int(headers[0]["trailer_start"], 16)
        window = spans[bisect_left(starts, front_end):bisect_left(starts, limit)]
        size = int(header["trailer_bytes"])
        candidates = list(trailer_candidates(directory, window, size))
        scopes.append((start, header, window, candidates))
        for trailer in candidates:
            families[(size, trailer.stored_hash)].append(start)

    print("pack_start\tword_24\ttrailer_bytes\ttrailer_candidates\tselected_trailer\tevidence\tstreams\taligned_groups\tpage_plus_0x10_starts")
    localized = []
    selected = []
    for start, header, window, candidates in scopes:
        size = int(header["trailer_bytes"])
        repeated = [
            span for span in candidates
            if len(set(families[(size, span.stored_hash)])) > 1
        ]
        exact = [span for span in candidates if span.detection == "exact_opaque_span"]
        plausible = repeated or exact or candidates
        if len(plausible) != 1:
            offsets = ",".join(f"{item.start:#x}" for item in plausible)
            print(f"{start:#x}\t{header['word_24']}\t{size}\t{len(candidates)}\t\t{offsets}\t\t\t")
            continue
        trailer = plausible[0]
        streams = [span for span in window if span.kind == "zlib" and span.end <= trailer.start]
        groups = stream_groups(streams)
        page_plus_16 = sum(group[0].start % PAGE_SIZE == 16 for group in groups)
        print(f"{start:#x}\t{header['word_24']}\t{size}\t{len(candidates)}\t"
              f"{trailer.start:#x}..{trailer.end:#x}\t{trailer.detection}\t"
              f"{len(streams)}\t{len(groups)}\t{page_plus_16}")
        selected.append((start, trailer))
        if repeated:
            localized.append((start, groups, trailer))
    return localized, selected


def ptr(data, offset):
    return struct.unpack_from("<Q", data, offset)[0] - 0x50000000


def survey_localized(directory, scopes, manifest):
    declared = [
        Path(item.text).name.removesuffix("_final.rpf")
        for item in ET.parse(manifest).findall("./fileList/Item/filename")
    ]
    print("\npack_start\tfirst_psin_valid\tfirst_psin_sha256\tfirst_resource_start\tstreams\tbytes\t"
          "decoded_root_pointer\tlanguage\tdeclared_in_order\tdecoded_text_offset")
    identified = {}
    for index, (start, groups, _) in enumerate(scopes):
        group = next((group for group in groups if group[0].start % PAGE_SIZE == 16), None)
        if group is None:
            continue
        first_psin = read_streams(directory, groups[0])
        data = read_streams(directory, group)
        hits = [
            (language, offset) for language, marker in LANGUAGE_MARKERS.items()
            if (offset := data.find(marker.encode())) >= 0
        ]
        language, offset = hits[0] if len(hits) == 1 else ("", -1)
        if language:
            identified[start] = language
        declared_at_index = declared[index] if index < len(declared) else ""
        print(f"{start:#x}\t{psin_valid(first_psin)}\t{sha256(first_psin).hexdigest()}\t"
              f"{group[0].start:#x}\t{len(group)}\t{len(data)}\t{ptr(data, 8):#x}\t"
              f"{language}\t{declared_at_index}\t{hex(offset) if offset >= 0 else ''}")
    return identified


def write_range(path, data, start, end):
    with path.open("xb") as output:
        output.write(memoryview(data)[start:end])


def survey_credits(directory, manifest, selected):
    raw_deflate_report = directory / "raw-deflate.tsv"
    if not raw_deflate_report.exists():
        return
    declared = [
        item.text for item in ET.parse(manifest).findall("./fileList/Item/filename")
        if Path(item.text).name == "credits.rpf"
    ]
    rows = [
        row for row in read_table(raw_deflate_report)
        if row["format_hint"].startswith("RBF0:uiCredits")
    ]
    print("\npack_start\tpack_end\traw_deflate_streams\tpages\tconfigs\tdeclared_path")
    for start, trailer in selected:
        records = [row for row in rows if start < int(row["start"], 16) < trailer.start]
        if records:
            pages = sum(row["format_hint"] == "RBF0:uiCreditsPageData" for row in records)
            configs = sum(row["format_hint"] == "RBF0:uiCreditsConfig" for row in records)
            print(f"{start:#x}\t{trailer.end:#x}\t{len(records)}\t{pages}\t{configs}\t{','.join(declared)}")


def export_nested(archive, directory, scopes, identified):
    nested = directory / "nested"
    nested.mkdir(exist_ok=True)
    with archive.open("rb") as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
        for start, trailer in scopes:
            name = f"{start:08x}"
            if start in identified:
                name += f"-{identified[start]}_final"
            path = nested / f"{name}.candidate.rpf"
            if not path.exists():
                write_range(path, data, start, trailer.end)


def existing_group_path(directory, group):
    first = group[0]
    size = sum(span.decoded_bytes for span in group)
    if first.file_offset == 0 and (directory / first.path).stat().st_size == size:
        return first.path
    return None


def export_localized(directory, scopes, identified):
    output = directory / "localized"
    output.mkdir(exist_ok=True)
    with (output / "groups.tsv").open("w", newline="") as report:
        writer = csv.writer(report, delimiter="\t", lineterminator="\n")
        writer.writerow(["language", "stored_start", "stored_end", "streams", "decoded_bytes", "file"])
        for start, groups, _ in scopes:
            language = identified.get(start)
            if not language:
                continue
            for group in groups:
                first = group[0]
                size = sum(span.decoded_bytes for span in group)
                path = existing_group_path(directory, group)
                if path is None:
                    path = f"localized/{language}/{first.start:08x}.bin"
                    target = directory / path
                    target.parent.mkdir(exist_ok=True)
                    target.write_bytes(read_streams(directory, group))
                writer.writerow([language, hex(first.start), hex(group[-1].end), len(group), size, path])


def survey_resource_names(directory, spans, selected, export):
    # This pack has a different fixed header suffix and begins with named
    # resources. A pointer back to the string distinguishes stored names
    # from coincidental printable bytes.
    headers = read_table(directory / "packs.tsv")
    different = {
        int(row["header_offset"], 16): int(row["front_end"], 16)
        for row in headers if row["shared_0x40"] == "false"
    }
    names = []
    checked = 0
    for start, trailer in selected:
        if start not in different:
            continue
        streams = [
            span for span in spans
            if span.kind == "zlib" and different[start] <= span.start and span.end <= trailer.start
        ]
        for group in stream_groups(streams):
            if group[0].start % PAGE_SIZE != 16:
                continue
            checked += 1
            data = read_streams(directory, group)
            file = None
            for suffix in RESOURCE_SUFFIX.finditer(data):
                name_end = suffix.start()
                name_start = data.rfind(b"\0", max(0, name_end - 128), name_end) + 1
                if not RESOURCE_NAME.fullmatch(data[name_start:name_end]):
                    continue
                pointer = struct.pack("<Q", 0x50000000 + name_start)
                stored_pointer = data.find(pointer)
                if stored_pointer < 0 or stored_pointer % 8:
                    continue
                name = data[name_start:suffix.end() - 1].decode("ascii")
                if export and file is None:
                    file = existing_group_path(directory, group)
                    if file is None:
                        file = f"named-resources/{group[0].start:08x}.bin"
                        target = directory / file
                        target.parent.mkdir(exist_ok=True)
                        target.write_bytes(data)
                names.append([
                    hex(start), hex(group[0].start), hex(group[-1].end),
                    hex(name_start), hex(stored_pointer), name, file,
                ])
    print(f"\nPage +0x10 groups checked for pointed resource names\t{checked}")
    print(f"Pointed resource name occurrences\t{len(names)}")
    print(f"Distinct pointed resource names\t{len({row[5] for row in names})}")
    if export:
        with (directory / "resource-names.tsv").open("w", newline="") as report:
            writer = csv.writer(report, delimiter="\t", lineterminator="\n")
            writer.writerow([
                "pack_start", "stored_start", "stored_end", "decoded_name_offset",
                "decoded_pointer_offset", "embedded_name", "file",
            ])
            writer.writerows(names)


def audit_psin(directory, spans, export):
    segments = defaultdict(list)
    for index, span in enumerate(spans):
        if span.kind == "zlib":
            segments[span.path].append(index)
    complete = 0
    incomplete = 0
    repaired = []
    for path, indices in segments.items():
        with (directory / path).open("rb") as source:
            if source.read(4) != b"PSIN":
                continue
            source.seek(0)
            data = source.read()
        if psin_valid(data):
            complete += 1
            continue
        incomplete += 1
        tail_index = indices[-1] + 1
        last_end = spans[indices[-1]].end
        if spans[tail_index].kind == "zero_run":
            tail_index += 1
        tail = spans[tail_index]
        if tail.kind != "unclassified" or tail.start != ((last_end + 15) & ~15):
            continue
        raw = (directory / tail.path).read_bytes()
        marker = 0
        while (marker := raw.find(b"CHKS\0\0\0\x14", marker)) >= 0:
            stop = marker + 0x14
            combined = data + raw[:stop]
            if psin_valid(combined):
                repaired.append((spans[indices[0]].start, tail.start, tail.start + stop, len(combined)))
                if export:
                    target = directory / "mixed-psin" / Path(path).name
                    target.parent.mkdir(exist_ok=True)
                    target.write_bytes(combined)
                break
            marker += 1
    print("\npsin_start\traw_tail_start\traw_tail_end\tdecoded_bytes")
    for start, tail, end, size in repaired:
        print(f"{start:#x}\t{tail:#x}\t{end:#x}\t{size}")
    print(f"\nPSIN chains with complete sections and matching CHKS length\t{complete}\t{complete + incomplete}")
    print(f"PSIN chains structurally completed by a raw tail\t{len(repaired)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="?", default=Path("output/data.rpf"))
    parser.add_argument("--language-manifest", type=Path, default=Path("output/common.rpf/decoded/0000d000.xml"))
    parser.add_argument("--credits-manifest", type=Path, default=Path("output/common.rpf/decoded/0000c000.xml"))
    parser.add_argument("--export-from", type=Path, help="source archive to copy candidate nested packs from")
    args = parser.parse_args()
    spans = [Span.from_row(row) for row in read_table(args.directory / "ranges.tsv")]
    localized, selected = survey_packs(args.directory, spans)
    identified = survey_localized(args.directory, localized, args.language_manifest)
    survey_credits(args.directory, args.credits_manifest, selected)
    audit_psin(args.directory, spans, args.export_from is not None)
    survey_resource_names(args.directory, spans, selected, args.export_from is not None)
    if args.export_from:
        export_nested(args.export_from, args.directory, selected, identified)
        export_localized(args.directory, localized, identified)


if __name__ == "__main__":
    main()
