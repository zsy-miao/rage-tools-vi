#!/usr/bin/env python3
"""Build a standalone, nested-quadrant view of verified RPF9 extraction manifests."""

import argparse
from bisect import bisect_right
import csv
import json
from pathlib import Path
import subprocess


def embedded_packs(cli, archive, manifest, timeout):
    with manifest.open(newline="", encoding="utf-8") as handle:
        headers = list(csv.DictReader(handle, delimiter="\t"))
    nested = len(headers) - 1
    if nested <= 0:
        return [], 0
    try:
        report = subprocess.check_output([cli, "partition", archive], text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"{archive}: pack inference timed out; keeping ranges at archive level")
        return [], nested
    packs = []
    for line in report.splitlines():
        if line.startswith("embedded_rpf9\t"):
            _, start, end, *_ = line.split("\t")
            pack = {"name": f"Pack {start}", "kind": "Pack · inferred bounds",
                    "start": int(start, 16), "end": int(end, 16), "children": []}
            if packs and pack["start"] < packs[-1]["end"]:
                raise ValueError(f"Overlapping pack extents in {archive}")
            packs.append(pack)
    return packs, max(0, nested - len(packs))


def read_archive(cli, archive, directory, timeout):
    packs, unresolved = embedded_packs(cli, archive, directory / "packs.tsv", timeout)
    starts = [pack["start"] for pack in packs]
    container = {"name": archive.name, "kind": "RPF9", "children": packs.copy(),
                 "unresolved_packs": unresolved}
    items = {}
    cursor = 0
    with (directory / "ranges.tsv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            start, end = int(row["start"], 16), int(row["end"], 16)
            if start != cursor or end <= start or end - start != int(row["stored_bytes"]):
                raise ValueError(f"Invalid range coverage in {archive} at {cursor:#x}")
            cursor = end
            path = row["file"]
            key = path or start
            if key not in items:
                items[key] = {"name": Path(path).name if path else f"{start:#x}",
                              "kind": row["kind"], "start": start, "end": end,
                              "stored": 0, "decoded": 0, "ranges": 0}
                if path:
                    items[key]["file"] = f"{archive.name}/{path}"
            item = items[key]
            item["end"] = end
            item["stored"] += end - start
            item["decoded"] += int(row["decoded_bytes"] or 0)
            item["ranges"] += 1
    if cursor != archive.stat().st_size:
        raise ValueError(f"Manifest size does not match {archive}")
    for item in items.values():
        index = bisect_right(starts, item["start"]) - 1
        if index >= 0 and item["end"] <= packs[index]["end"]:
            packs[index]["children"].append(item)
        else:
            container["children"].append(item)
    container["stored"] = cursor
    container["ranges"] = sum(item["ranges"] for item in items.values())
    return container


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("."))
    parser.add_argument("--extraction", type=Path, default=Path("output/general-extraction"))
    parser.add_argument("--cli", type=Path, default=Path("target/release/rage-tools-vi"))
    parser.add_argument("--pack-timeout", type=float, default=3,
                        help="seconds per archive for candidate pack bounds (default: 3)")
    args = parser.parse_args()
    if args.pack_timeout <= 0:
        parser.error("--pack-timeout must be greater than zero")
    archives = sorted(args.source.glob("*.rpf"))
    if not archives:
        parser.error(f"no .rpf files in {args.source}")
    roots = [read_archive(args.cli.resolve(), archive, args.extraction / archive.name, args.pack_timeout)
             for archive in archives]
    payload = json.dumps(roots, separators=(",", ":"), ensure_ascii=True).replace("<", "\\u003c")
    index = args.extraction / "index.html"
    index.write_text(HTML.replace("__ARCHIVES__", payload), encoding="utf-8")
    print(f"{index}: {len(roots)} archives, {sum(root['ranges'] for root in roots):,} ranges")


HTML = '''<!doctype html>
<html lang="pt-BR">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Extração RPF9</title>
<style>
:root{color-scheme:dark;--bg:#141820;--panel:#202733;--line:#424e60;--accent:#a9e0c0}
*{box-sizing:border-box}body{max-width:64rem;margin:auto;padding:clamp(1rem,4vw,3rem);font:1rem system-ui;background:var(--bg);color:#eef1f4}
h1{font-size:clamp(1.5rem,5vw,2.3rem);margin:0 0 1rem} button{font:inherit;color:inherit;cursor:pointer}
#trail{display:flex;align-items:center;gap:.75rem;flex-wrap:wrap;margin-bottom:1rem;overflow-wrap:anywhere}
#back{border:1px solid var(--line);background:var(--panel);padding:.4rem .8rem;border-radius:.4rem}
#back:disabled{opacity:.45;cursor:default} #tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.65rem;padding:.65rem;border:1px solid var(--line);border-radius:.6rem}
.tile{min-height:clamp(7rem,23vw,12rem);text-align:left;display:flex;flex-direction:column;justify-content:space-between;gap:.5rem;background:var(--panel);border:1px solid var(--line);border-radius:.4rem;padding:clamp(.7rem,3vw,1.4rem);overflow-wrap:anywhere}
.tile:hover,.tile:focus-visible{border-color:var(--accent)}.tile span{color:var(--accent);font-size:.8rem}.tile strong{font-size:clamp(.9rem,3vw,1.25rem)}
#details{margin:0;padding:1rem;border:1px solid var(--line);border-radius:.6rem;white-space:pre-wrap;overflow-wrap:anywhere;font:1rem/1.7 ui-monospace,monospace}
</style>
<h1>Extração RPF9</h1>
<nav id="trail" aria-label="Caminho atual"><button id="back" type="button">Voltar</button><span id="path"></span></nav>
<main><p id="unresolved" hidden></p><section id="tiles" aria-label="Quadrantes"></section><pre id="details" hidden></pre></main>
<script id="data" type="application/json">__ARCHIVES__</script>
<script>
const archives = JSON.parse(document.getElementById('data').textContent);
const tiles = document.getElementById('tiles');
const details = document.getElementById('details');
const back = document.getElementById('back');
const stack = [{name:'Arquivos', children:archives}];
const number = new Intl.NumberFormat('pt-BR');
const hex = value => '0x' + value.toString(16);

function quadrants(children) {
  if (children.length <= 4) return children;
  const size = Math.ceil(children.length / 4);
  const groups = [];
  for (let start = 0; start < children.length; start += size) {
    const group = children.slice(start, start + size);
    groups.push({name:group[0].name + ' … ' + group.at(-1).name,
                 kind:'Quadrante', children:group});
  }
  return groups;
}

function render() {
  const current = stack.at(-1);
  back.disabled = stack.length === 1;
  document.getElementById('path').textContent = stack.map(node => node.name).join(' › ');
  const unresolved = document.getElementById('unresolved');
  unresolved.hidden = !current.note && !current.unresolved_packs;
  unresolved.textContent = current.note ?? (current.unresolved_packs + ' cabeçalhos de packs sem limites confirmados');
  tiles.replaceChildren();
  const children = current.children;
  tiles.hidden = !children?.length;
  tiles.style.display = tiles.hidden ? 'none' : '';
  details.hidden = !tiles.hidden;
  if (tiles.hidden) {
    const lines = [current.kind];
    if (current.start !== undefined) lines.push('Extensão na origem: ' + hex(current.start) + ' até ' + hex(current.end) + ' (fim exclusivo)');
    if (current.ranges !== undefined) lines.push('Intervalos: ' + number.format(current.ranges));
    if (current.stored !== undefined) lines.push('Bytes armazenados: ' + number.format(current.stored));
    if (current.decoded) lines.push('Bytes decodificados: ' + number.format(current.decoded));
    if (current.file) lines.push('Arquivo extraído: ' + current.file);
    if (current.source) lines.push('Arquivo de origem: ' + current.source);
    if (current.manifest) lines.push('Manifesto da extração: ' + current.manifest);
    if (current.sha256) lines.push('SHA-256: ' + current.sha256);
    if (current.availability) lines.push(current.availability);
    if (current.kind === 'zero_run') lines.push('Preenchimento com zeros, registrado no manifesto.');
    details.textContent = lines.join(String.fromCharCode(10));
    if (current.stream_index) {
      const link = document.createElement('a');
      link.href = current.stream_index;
      link.download = '';
      link.textContent = 'Baixar índice de fluxos zlib (TSV)';
      details.append(document.createElement('br'), link);
    }
    return;
  }
  const visible = stack.length === 1 && children.length <= 8 ? children : quadrants(children);
  for (const child of visible) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'tile';
    const title = document.createElement('strong');
    title.textContent = child.name;
    const meta = document.createElement('span');
    const count = child.ranges ?? child.children?.length;
    meta.textContent = child.kind + (count === undefined ? '' : ' · ' + number.format(count));
    button.append(title, meta);
    button.addEventListener('click', () => {
      stack.push(child);
      render();
      (tiles.querySelector('button') ?? back).focus();
    });
    tiles.append(button);
  }
}

back.addEventListener('click', () => {
  stack.pop();
  render();
  (tiles.querySelector('button') ?? back).focus();
});
render();
</script>
</html>
'''


if __name__ == "__main__":
    main()
