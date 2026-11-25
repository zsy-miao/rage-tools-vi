"""Match JOAAT field names in the decoded PSIN sections."""

import argparse
from collections import Counter
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from section_blocks import read_records  # noqa: E402

CURATED = {
    "name",
    "attributes",
    "flags",
    "heading",
    "root",
    "car_hydraulics",
}
SECTION_HEADERS = {
    "PSIN": 8,
    "LSCH": 16,
    "LENM": 8,
    "LSNS": 12,
    "LRSC": 16,
}


def joaat(text):
    value = 0
    for byte in text.encode():
        value = (value + byte) & 0xFFFFFFFF
        value = (value + (value << 10)) & 0xFFFFFFFF
        value ^= value >> 6
    value = (value + (value << 3)) & 0xFFFFFFFF
    value ^= value >> 11
    value = (value + (value << 15)) & 0xFFFFFFFF
    return value & 0xFFFFFFFF


def candidates(archive_dir):
    result = set(CURATED)
    for path in (archive_dir / "output").rglob("*.xml"):
        text = path.read_text(errors="ignore")
        tokens = set(re.findall(r"[A-Za-z0-9_.-]+", text))
        result |= tokens
        for token in tokens:
            for part in re.split(r"[._/-]+", token):
                if len(part) >= 2:
                    result.add(part)
    wordlist = Path("/usr/share/dict/words")
    if wordlist.is_file():
        result |= {line.strip() for line in wordlist.read_text(errors="ignore").splitlines() if line.strip()}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--archive-dir", type=Path, default=Path("."))
    parser.add_argument("--section", default=None)
    parser.add_argument("--limit", type=int, default=80)
    args = parser.parse_args()

    records = read_records(args.cli, args.archive, 0xC4000, 0x4282B0)
    names = candidates(args.archive_dir)
    lookup = {}
    for name in names:
        for variant in {name, name.lower()}:
            lookup.setdefault(joaat(variant), set()).add(variant)

    hits = Counter()
    examples = {}
    for record_index, sections in enumerate(records):
        for section, header in SECTION_HEADERS.items():
            if args.section and section != args.section:
                continue
            body = sections.get(section, b"")
            payload = body[header:]
            for offset in range(0, len(payload) - 3, 4):
                value = struct.unpack_from("<I", payload, offset)[0]
                if value not in lookup:
                    continue
                labels = tuple(sorted(lookup[value]))
                hits[(section, offset, value, labels)] += 1
                examples.setdefault((section, offset, value, labels), (record_index, offset))

    print(f"records: {len(records)}")
    print(f"candidate hashes: {len(lookup)}")
    print(f"matches: {len(hits)}")
    print("section\toffset\thash\tnames\tcount\texample_record")
    for (section, offset, value, labels), count in hits.most_common(args.limit):
        record_index, _ = examples[(section, offset, value, labels)]
        print(
            f"{section}\t0x{offset:03x}\t0x{value:08x}\t{','.join(labels)}\t"
            f"{count}\t{record_index}"
        )


if __name__ == "__main__":
    main()
