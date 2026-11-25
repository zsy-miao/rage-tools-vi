"""End-to-end mod check: replace a zlib range in a copy, then read it back.

    python3 tests/test_mod_roundtrip.py [ARCHIVE] [START] [END]
"""

import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from rage import pack_replacement  # noqa: E402

FAILED = []


def check(name, condition, detail=""):
    print(f"  {'ok  ' if condition else 'FAIL'}  {name} {detail}")
    if not condition:
        FAILED.append(name)


def main():
    archive = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "common.rpf"
    start = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x3B2850
    end = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x3B399E
    if not archive.is_file():
        print("  skipped (archive not present)")
        return 0
    with tempfile.TemporaryDirectory() as work:
        copy = Path(work) / "mod.rpf"
        copy.write_bytes(archive.read_bytes())
        before = copy.stat().st_size
        stored = copy.read_bytes()[start:end]
        packed = pack_replacement(b"E2E_OK", len(stored))
        check("replacement fits the stored room", packed is not None)
        with copy.open("r+b") as handle:
            handle.seek(start)
            handle.write(packed)
        data = copy.read_bytes()
        check("payload reads back", zlib.decompress(data[start:end]) == b"E2E_OK")
        check("archive size unchanged", copy.stat().st_size == before)
    print()
    print("PASS" if not FAILED else f"FAIL: {len(FAILED)} check(s)")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
