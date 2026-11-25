"""Smoke tests for the naming and PSIN tools.

Plain assertions, no framework: the point is that a fresh clone can run one
command and know whether the registry, the annotator and the schema readers
still work against the committed data.

    python3 tests/test_analysis_tools.py
"""
import csv
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILED = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILED.append(name)


def run(*args):
    return subprocess.run([sys.executable, *args], cwd=ROOT,
                          capture_output=True, text=True)


def main():
    # The archive alone is not enough for the archive-side checks: they also need
    # the stream index, which lives on an external volume and is absent on a fresh
    # clone. Without this guard the suite fails instead of skipping.
    have_archive = (ROOT / "script.rpf").is_file()
    have_index = (ROOT / "output/index/script.tsv").is_file()

    print("registry")
    result = run("tools/name_registry.py", "--lookup", "0x01166164", "0xdeadbeef")
    check("lookup resolves a known hash", "Position" in result.stdout)
    check("lookup reports an unknown hash", "<unresolved>" in result.stdout)
    check("lookup exits non-zero when a hash is unresolved", result.returncode == 1)

    names = list(csv.DictReader((ROOT / "handoff/names.tsv").open(), delimiter="\t"))
    check("registry has at least 30k names", len(names) > 30000, f"({len(names)})")
    required = {"hash", "name", "kind", "confidence", "source",
                "also_known_as", "ambiguous"}
    check("registry columns", required <= set(names[0]), set(names[0]))
    check("a collision is marked ambiguous",
          any(row["ambiguous"] == "1" for row in names))

    print("annotation")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "named.tsv"
        result = run("tools/name_registry.py", "--annotate",
                     "handoff/script-bones.tsv", "--column", "bone_hash",
                     "--out", str(out))
        check("annotate succeeds", result.returncode == 0, result.stderr[:120])
        rows = list(csv.DictReader(out.open(), delimiter="\t"))
        check("annotate adds name columns", "name_confidence" in rows[0])
        check("annotate names some rows", any(row["name"] for row in rows))

    print("PSIN")
    properties = ROOT / "cache/psin-properties.tsv"
    if not properties.is_file():
        print("  skipped (no cache/psin-properties.tsv; "
              "tools/psin_extract.py creates it)")
    else:
        print("PSIN")
        result = run("tools/psin_dump.py", "--property", "position")
        check("property search finds records", "records mention" in result.stdout)
        result = run("tools/psin_segment.py", "--describe", "1054")
        check("describe prints entries", "Id=" in result.stdout)
        check("describe pairs Id and Type",
              any("Type=" in line and "Id=" in line for line in result.stdout.splitlines()))

        (ROOT / "cache").mkdir(exist_ok=True)
        result = run("tools/psin_entries.py", "--out", "cache/psin-entries-test.tsv")
        check("entries extraction runs", result.returncode == 0, result.stderr[:120])
        entries = list(csv.DictReader((ROOT / "cache/psin-entries-test.tsv").open(),
                                      delimiter="\t"))
        check("entries found", len(entries) > 1000, f"({len(entries)})")
        check("entries carry Id/Type pairs",
              any(row["field_a"] in ("Id", "Type") for row in entries))

    if have_archive and have_index:
        print("extraction from the archive")
        result = run("tools/psin_extract.py", "script.rpf",
                     "--out", "cache/psin-properties-test.tsv")
        check("extract runs", result.returncode == 0, result.stderr[:120])
        rows = list(csv.DictReader((ROOT / "cache/psin-properties-test.tsv").open(),
                                   delimiter="\t"))
        check("extract finds the same 62,910 rows", len(rows) == 62910, f"({len(rows)})")
        check("extract column layout", "class_hash" in rows[0], set(rows[0]))
    else:
        print("extraction from the archive: skipped (archive or index not present)")

    print("script metadata format")
    result = run("tools/script_meta.py", "--help")
    check("script_meta runs", result.returncode == 0, result.stderr[:120])
    result = run("tools/psin_blocks.py", "--help")
    check("psin_blocks runs", result.returncode == 0, result.stderr[:120])

    sections = list(csv.DictReader((ROOT / "handoff/script-sections.tsv").open(),
                                   delimiter="\t"))
    check("script-sections table exists", len(sections) > 4000, f"({len(sections)})")
    check("script-sections columns",
          {"record", "tag", "block_bytes", "block_rows"} <= set(sections[0]),
          set(sections[0]))
    check("section tags are 32-bit values",
          all(row["tag"].startswith("0x") and len(row["tag"]) == 10
              for row in sections[:100]))

    rows = list(csv.DictReader((ROOT / "handoff/psin-rows.tsv").open(), delimiter="\t"))
    check("typed rows table has 63,288 rows", len(rows) == 63288, f"({len(rows)})")
    check("typed rows columns", {"a", "b", "c", "type"} <= set(rows[0]), set(rows[0]))
    check("the type word is one of the five known types",
          {row["type"] for row in rows} <= {"0x101", "0x102", "0x103", "0x104", "0x105"},
          {row["type"] for row in rows})

    if (ROOT / "script.rpf").is_file() and have_index:
        result = run("tools/script_meta.py", "--dump", "1")
        check("script_meta walks a record", result.returncode == 0, result.stderr[:120])
        check("every record reaches LRSC",
              "LRSC" in result.stdout and "PSIN" in result.stdout)
        result = run("tools/script_meta.py", "--verify")
        check("the chain covers every body exactly", result.returncode == 0,
              result.stdout[-160:] if result.returncode else "")
        check("no record is short of chunks",
              "chain covers the body exactly: 1012/1012" in result.stdout,
              result.stdout[-160:])
    else:
        print("script_meta over the archive: skipped (archive or index not present)")

    print("game name hash")
    result = run("tools/name_hash_game.py", "--hash", "trailers")
    check("hash tool runs", result.returncode == 0, result.stderr[:120])
    # The executable compares against these values as inline mov immediates, which
    # makes them independent confirmations of the implementation.
    check("murmur3-x64-128 of 'trailers' matches the engine",
          "0xfe29572e616c25ad" in result.stdout, result.stdout.strip()[:80])

    exe = ROOT / "cache/exe/game_scarlett_master.exe"
    if exe.is_file():
        result = run("tools/name_hash_game.py", "--probe", "script.rpf")
        check("hash probe runs", result.returncode == 0, result.stderr[:120])
        result = run("tools/pe_scan.py", "sections")
        check("pe_scan reads the section table", ".text" in result.stdout)
        check("pe_scan places .text at the right base", "0x140001000" in result.stdout)
        result = run("tools/pe_scan.py", "sbox")
        check("no AES forward S-box in the image", "AES forward sbox: 0" in result.stdout)
    else:
        print("pe_scan: skipped (executable not present)")

    print()
    if FAILED:
        print(f"FAIL: {len(FAILED)} check(s) failed: {', '.join(FAILED)}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
