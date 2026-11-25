"""Write `docs/reference/tools.md` from the tools' own docstrings.

Every script in `tools/` starts with a one-line summary followed by usage. This
reads that summary, plus any `--help`-visible argument names, and emits one table
so the published docs cannot drift from the code.

    python3 tools/tool_index.py            # write the page
    python3 tools/tool_index.py --check    # fail if the page is out of date
"""

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
PAGE = ROOT / "docs/reference/tools.md"

HEADER = """# Tools

Every script in `tools/` at a glance. The summary column comes from each file's own
docstring, so this page is generated, not maintained by hand:

```sh
python3 tools/tool_index.py          # regenerate
python3 tools/tool_index.py --check  # verify the page matches the code
```

Run any tool with `--help` for its arguments. Most read from the repository root
so `python3 tools/<name>.py` works without arguments.
"""


def summarise(path):
    try:
        module = ast.parse(path.read_text())
    except SyntaxError:
        return "*(does not parse)*", ""
    doc = ast.get_docstring(module) or ""
    lines = [line.strip() for line in doc.strip().splitlines() if line.strip()]
    if not lines:
        return "", ""
    summary = lines[0]
    flags = sorted({word for line in lines for word in line.split()
                    if word.startswith("--") and len(word) > 2})
    return summary, " ".join(flags[:6])


def collect():
    rows = []
    for path in sorted(TOOLS.glob("*.py")):
        if path.name.startswith("_"):
            continue
        summary, flags = summarise(path)
        rows.append((path.name, summary, flags))
    return rows


def render(rows):
    out = [HEADER, "", f"{len(rows)} scripts.", "",
           "| Tool | Purpose | Notable flags |", "| --- | --- | --- |"]
    for name, summary, flags in rows:
        clean = summary.replace("|", "\\|")
        out.append(f"| [`{name}`](https://github.com/lynxnathan/rage-tools-vi/blob/main/tools/{name}) "
                   f"| {clean} | {flags} |")
    out.append("")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true",
                        help="exit non-zero if the page is out of date")
    args = parser.parse_args()

    rows = collect()
    text = render(rows)
    if args.check:
        if not PAGE.is_file():
            print(f"missing {PAGE.relative_to(ROOT)}")
            return 1
        if PAGE.read_text() != text:
            print(f"{PAGE.relative_to(ROOT)} is out of date; run tools/tool_index.py")
            return 1
        print(f"{PAGE.relative_to(ROOT)} is current ({len(rows)} tools)")
        return 0
    PAGE.parent.mkdir(parents=True, exist_ok=True)
    PAGE.write_text(text)
    print(f"wrote {PAGE.relative_to(ROOT)} ({len(rows)} tools)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
