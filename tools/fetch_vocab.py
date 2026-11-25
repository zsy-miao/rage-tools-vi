"""Fetch the engine's own name table as a hash vocabulary.

Our harvested corpus is model, bone and variant strings; the engine's *metadata*
names are a different namespace (`flags`, `blendduration`, `bumper_f`, ...).
CodeWalker's `MetaNames.cs` is the public mirror of that table: an enum of
20,300 structure, member and enum names, MIT licensed.

The file is downloaded into `cache/vocab/` (untracked) and reduced to one name
per line, so the registry can hash it without depending on the network.

    python3 tools/fetch_vocab.py
"""
import argparse
import re
import sys
import urllib.request
from pathlib import Path

URL = ("https://raw.githubusercontent.com/dexyfex/CodeWalker/master/"
       "CodeWalker.Core/GameFiles/MetaTypes/MetaNames.cs")
ENTRY = re.compile(r"^\s*([A-Za-z_@][A-Za-z0-9_]*)\s*=\s*(\d+),", re.M)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("cache/vocab/codewalker-names.txt"))
    parser.add_argument("--source", default=URL)
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    raw = args.out.with_suffix(".cs")
    if raw.is_file():
        text = raw.read_text(errors="ignore")
    else:
        print(f"downloading {args.source}")
        text = urllib.request.urlopen(args.source, timeout=60).read().decode("utf-8", "ignore")
        raw.write_text(text)
    names = sorted({name.lstrip("@") for name, _ in ENTRY.findall(text)})
    if not names:
        sys.exit("no enum entries found; the upstream file may have moved")
    args.out.write_text("\n".join(names) + "\n")
    print(f"{len(names)} names -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
