#!/usr/bin/env python3
"""Build one resource-local XY quadtree per class-0 root and an HTML view."""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

CAPACITY = 8
MAX_DEPTH = 8


class Node:
    __slots__ = ("x0", "y0", "x1", "y1", "depth", "items", "children")

    def __init__(self, x0, y0, x1, y1, depth=0):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.depth = depth
        self.items = []
        self.children = [None, None, None, None]


def quadrant(node, rect):
    x0, y0, x1, y1 = rect
    mx = (node.x0 + node.x1) / 2
    my = (node.y0 + node.y1) / 2
    if x0 < mx < x1 or y0 < my < y1:
        return None
    east = x0 >= mx
    south = y0 >= my
    return (1 if east else 0) + (2 if south else 0)


def insert(node, item, rect):
    if len(node.items) < CAPACITY or node.depth >= MAX_DEPTH:
        node.items.append((item, rect))
        return
    q = quadrant(node, rect)
    if q is None:
        node.items.append((item, rect))
        return
    if node.children[q] is None:
        mx = (node.x0 + node.x1) / 2
        my = (node.y0 + node.y1) / 2
        if q & 1:
            cx0, cx1 = mx, node.x1
        else:
            cx0, cx1 = node.x0, mx
        if q & 2:
            cy0, cy1 = my, node.y1
        else:
            cy0, cy1 = node.y0, my
        node.children[q] = Node(cx0, cy0, cx1, cy1, node.depth + 1)
    insert(node.children[q], item, rect)


def serialise(node):
    return {
        "bounds": [node.x0, node.y0, node.x1, node.y1],
        "depth": node.depth,
        "items": [{"id": item, "rect": rect} for item, rect in node.items],
        "children": [serialise(child) for child in node.children if child],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("geometry", type=Path, nargs="?", default=Path("handoff/script-bone-geometry.tsv"))
    parser.add_argument("--json", type=Path, default=Path("output/script-quadtree/script-quadtree.json"))
    parser.add_argument("--html", type=Path, default=Path("output/script-quadtree/index.html"))
    parser.add_argument("--summary", type=Path, default=Path("handoff/script-quadtree-summary.tsv"))
    args = parser.parse_args()

    roots = defaultdict(list)
    with args.geometry.open(newline="", encoding="utf-8") as handle:
        import csv
        for row in csv.DictReader(handle, delimiter="\t"):
            if int(row["points"]) == 0:
                continue
            rect = tuple(float(row[key]) for key in ("min_x", "min_y", "max_x", "max_y"))
            if not all(map(math.isfinite, rect)) or rect[0] > rect[2] or rect[1] > rect[3]:
                continue
            item = {
                "root_id": row["root_id"],
                "table_record": int(row["table_record"]),
                "bone_index": int(row["bone_index"]),
                "bone_hash": row["bone_hash"],
                "points": int(row["points"]),
            }
            roots[row["root_id"]].append((item, rect))

    trees = {}
    summary = []
    for root_id, entries in sorted(roots.items()):
        x0 = min(rect[0] for _, rect in entries)
        y0 = min(rect[1] for _, rect in entries)
        x1 = max(rect[2] for _, rect in entries)
        y1 = max(rect[3] for _, rect in entries)
        if x0 == x1:
            x0, x1 = x0 - 0.5, x1 + 0.5
        if y0 == y1:
            y0, y1 = y0 - 0.5, y1 + 0.5
        tree = Node(x0, y0, x1, y1)
        for item, rect in entries:
            insert(tree, item, rect)
        nodes = serialise(tree)

        def count_nodes(node):
            return 1 + len(node["children"]) + sum(count_nodes(child) for child in node["children"])

        def max_depth(node):
            return max([node["depth"]] + [max_depth(child) for child in node["children"]])

        trees[root_id] = nodes
        summary.append((
            root_id, len(entries), count_nodes(nodes), max_depth(nodes),
            f"{x0:.6g}", f"{y0:.6g}", f"{x1:.6g}", f"{y1:.6g}",
        ))

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(trees, separators=(",", ":")))
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    with args.summary.open("w", encoding="utf-8", newline="") as handle:
        import csv
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["root_id", "items", "nodes", "max_depth", "x0", "y0", "x1", "y1"])
        writer.writerows(summary)

    args.html.parent.mkdir(parents=True, exist_ok=True)
    embedded = json.dumps(trees, separators=(",", ":"))
    args.html.write_text(HTML.replace("__DATA__", embedded))

    print(f"roots: {len(trees)}; items: {sum(len(entries) for entries in roots.values())}")
    print("root_id\titems\tnodes\tmax_depth")
    for row in summary[:10]:
        print(f"{row[0]}\t{row[1]}\t{row[2]}\t{row[3]}")


HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Class-0 quadtree</title>
<style>
body{font-family:system-ui,sans-serif;margin:1rem;background:#0f172a;color:#e2e8f0}
select,button{font:inherit;padding:.25rem .4rem}
#wrap{display:flex;gap:1rem;align-items:flex-start;flex-wrap:wrap}
#svg{background:#111827;border:1px solid #334155;width:min(78vw,900px);height:min(78vw,900px)}
.legend{font-size:.8rem;color:#94a3b8;max-width:260px}
</style></head><body>
<h1>Class-0 quadtree</h1>
<div id="wrap"><div><select id="root"></select> <button id="fit">Fit</button><br>
<svg id="svg" viewBox="0 0 1000 1000"></svg></div>
<div class="legend">One tree per class-0 root. Resource-local XY bounds, closed
rectangles, split-spanning items retained at the current node. Node borders show
quadtree depth; cyan rectangles are decoded bone bounds.</div></div>
<script id="data" type="application/json">__DATA__</script>
<script>
const trees=JSON.parse(document.getElementById('data').textContent);
const rootSel=document.getElementById('root'), svg=document.getElementById('svg');
const roots=Object.keys(trees).sort();
for(const r of roots){const o=document.createElement('option');o.value=r;o.textContent=r;rootSel.appendChild(o)}
const NS='http://www.w3.org/2000/svg';
function el(name,attrs){const e=document.createElementNS(NS,name);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);return e}
let view={x:0,y:0,w:1000,h:1000};
function map(rect){return {x:(rect[0]-view.x)/view.w*1000,y:(rect[1]-view.y)/view.h*1000,w:(rect[2]-rect[0])/view.w*1000,h:(rect[3]-rect[1])/view.h*1000}}
function walk(node,cb){cb(node);for(const c of node.children)walk(c,cb)}
function draw(){
  const tree=trees[rootSel.value]; if(!tree)return;
  view={x:tree.bounds[0],y:tree.bounds[1],w:tree.bounds[2]-tree.bounds[0],h:tree.bounds[3]-tree.bounds[1]};
  if(view.w<=0)view.w=1; if(view.h<=0)view.h=1;
  svg.replaceChildren();
  walk(tree,node=>{
    const r=map(node.bounds);
    svg.appendChild(el('rect',{x:r.x,y:r.y,width:r.w,height:r.h,fill:'none',stroke:`hsla(${180+node.depth*25},80%,60%,.35)`, 'stroke-width':1}));
    for(const it of node.items){
      const q=map(it.rect);
      svg.appendChild(el('rect',{x:q.x,y:q.y,width:Math.max(q.w,.4),height:Math.max(q.h,.4),fill:'none',stroke:'#22d3ee','stroke-width':1}));
      const t=el('title',{});t.textContent=`${it.id.root_id} table=${it.id.table_record} bone=${it.id.bone_index} points=${it.id.points}`;svg.lastChild.appendChild(t);
    }
  });
}
rootSel.addEventListener('change',draw);
document.getElementById('fit').addEventListener('click',draw);
draw();
</script></body></html>'''

if __name__ == "__main__":
    main()
