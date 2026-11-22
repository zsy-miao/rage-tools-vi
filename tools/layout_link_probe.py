"""Test structured vehicle-model/layout pairs against class-0 layout roots."""

import argparse
from collections import Counter
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from object_names import extract_object, parse_tree  # noqa: E402
from root_names import joaat  # noqa: E402


def layout_variants(name):
    base = name[7:] if name.upper().startswith("LAYOUT_") else name
    return {
        name,
        name.lower(),
        name.upper(),
        base,
        base.lower(),
        "layout_" + base.lower(),
        "LAYOUT_" + base.upper(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?", default=Path("script.rpf"))
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--meta", nargs="+", type=Path, default=[Path("/tmp/vehicles2.meta")])
    parser.add_argument("--common-xml", type=Path, default=Path("output/common.rpf"))
    parser.add_argument(
        "--tsv", type=Path, default=Path("output/script.rpf/layout-links.tsv")
    )
    args = parser.parse_args()

    data = extract_object(args.cli, args.archive)
    count, offsets, roots, children, root_of = parse_tree(data)
    class0 = set()
    all_roots = set()
    for root in roots:
        identifier = struct.unpack_from("<I", data, offsets[root])[0]
        all_roots.add(identifier)
        high = struct.unpack_from("<I", data, offsets[root] + 4)[0] >> 16
        if high == 0:
            class0.add(identifier)

    pairs = []
    for path in args.meta:
        text = path.read_text(errors="ignore")
        for match in re.finditer(
            r"<modelName>([^<]+)</modelName>.*?<layout>([^<]*)</layout>",
            text,
            re.S,
        ):
            model, layout = match.group(1).strip(), match.group(2).strip()
            if model and layout:
                pairs.append((path.name, model, layout))

    rows = []
    for source, model, layout in pairs:
        for variant in layout_variants(layout):
            identifier = joaat(variant)
            rows.append(
                {
                    "source": source,
                    "model": model,
                    "layout": layout,
                    "variant": variant,
                    "hash": identifier,
                    "class0": identifier in class0,
                    "root": identifier in all_roots,
                }
            )

    out = args.tsv
    out.parent.mkdir(parents=True, exist_ok=True)
    columns = ["source", "model", "layout", "variant", "hash", "class0", "root"]
    with out.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(columns) + "\n")
        for row in rows:
            handle.write(
                "\t".join(str(row[column]) for column in columns) + "\n"
            )

    class0_hits = [row for row in rows if row["class0"]]
    root_hits = [row for row in rows if row["root"]]
    print(f"meta files: {len(args.meta)}")
    print(f"model/layout pairs: {len(pairs)}")
    print(f"distinct models: {len({pair[1] for pair in pairs})}")
    print(f"distinct layouts: {len({pair[2] for pair in pairs})}")
    print(f"hash variants tested: {len(rows)}")
    print(f"class-0 matches: {len(class0_hits)}")
    print(f"any-root matches: {len(root_hits)}")
    if pairs:
        source, model, layout = pairs[0]
        identifier = joaat(layout.lower())
        print(
            f"example: {source} model={model} layout={layout} "
            f"joaat(lower)=0x{identifier:08x} class0={identifier in class0} root={identifier in all_roots}"
        )
    if class0_hits:
        for row in class0_hits[:10]:
            print(
                f"MATCH {row['source']} {row['model']} {row['layout']} "
                f"variant={row['variant']} hash=0x{row['hash']:08x}"
            )

    if args.common_xml.is_dir():
        layout_tags = 0
        vehicle_names = 0
        files = 0
        for path in args.common_xml.glob("*.xml"):
            files += 1
            text = path.read_text(errors="ignore")
            layout_tags += len(re.findall(r"<layout>", text))
            vehicle_names += len(re.findall(r"<vehicleModelName>", text))
        print(f"common XML files: {files}, <layout> tags: {layout_tags}, vehicleModelName tags: {vehicle_names}")
    print(f"tsv: {out}")


if __name__ == "__main__":
    main()
