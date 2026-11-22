#!/usr/bin/env python3
"""Reproducible RPF9 output pipeline.

Subcommands:
  index    bounded zlib range indexes for all eight large archives
  extract  bulk extraction + verification for six selected archives
  audio    rebuild AWC / XMA2 / Opus / ACE1 output from audio.rpf
  pilot    build the eight-root static extraction browser
  verify   verify every extracted manifest against its index
  all      index -> extract -> audio -> pilot -> verify

Safety: an existing non-empty output requires --resume (continue) or --force
(delete and regenerate).  --dry-run prints the exact commands without touching
the output tree.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = {
    "anim": "anim.rpf",
    "packs": "packs.rpf",
    "navmeshes": "navmeshes.rpf",
    "core_bvh4": "pack/core_bvh4/core_bvh4.rpf",
    "story000": "pack/story000/story000.rpf",
    "audio": "audio.rpf",
    "movies": "movies.rpf",
    "levels": "levels.rpf",
}
EXTRACTED = ("anim", "packs", "navmeshes", "core_bvh4", "story000", "audio", "levels")


def log(record: dict, out: Path, dry: bool):
    if dry:
        return
    out.mkdir(parents=True, exist_ok=True)
    with (out / "pipeline-runs.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def guard(path: Path, force: bool, resume: bool, what: str, dry: bool = False):
    if not path.exists():
        return
    if force:
        if not dry:
            shutil.rmtree(path)
        return
    if resume:
        return
    if any(path.iterdir()):
        raise SystemExit(f"{what} exists at {path}; use --resume or --force")


def run(command: list[str], out: Path, dry: bool, label: str):
    print("+ " + " ".join(command))
    if dry:
        return
    record = {"label": label, "command": command}
    env = {**os.environ, "PYTHON": os.environ.get("PYTHON", sys.executable)}
    result = subprocess.run(command, cwd=ROOT, text=True, env=env)
    record["returncode"] = result.returncode
    log(record, out, dry)
    if result.returncode:
        raise SystemExit(f"{label} failed ({result.returncode})")


def source_map(source: Path) -> dict[str, Path]:
    missing = [str(source / rel) for rel in ARCHIVES.values() if not (source / rel).is_file()]
    if missing:
        raise SystemExit("missing source archives:\n  " + "\n  ".join(missing))
    return {name: source / rel for name, rel in ARCHIVES.items()}


def index(source: Path, out: Path, args):
    index_dir = out / "index"
    if args.force and not args.dry_run:
        shutil.rmtree(index_dir, ignore_errors=True)
    for name, archive in source_map(source).items():
        target = index_dir / f"{name}.tsv"
        if target.exists() and not args.force:
            print(f"= index exists: {target} (use --force to replace)")
            continue
        run([sys.executable, "tools/stream_index.py", str(archive), "--out", str(target)],
            out, args.dry_run, f"index:{name}")


def extract(source: Path, out: Path, args):
    archives = source_map(source)
    for name in args.archives:
        archive = archives[name]
        index_path = out / "index" / f"{name}.tsv"
        target = out / "extracted" / name
        manifest = target / "manifest.tsv"
        if not index_path.is_file() and not args.dry_run:
            raise SystemExit(f"index missing for {name}: {index_path}")
        guard(target, args.force, args.resume, f"{name} extraction", args.dry_run)
        command = [sys.executable, "tools/bulk_extract.py", str(archive),
                   str(index_path), str(target), "--workers", str(args.workers),
                   "--manifest", str(manifest)]
        if args.resume:
            command.append("--resume")
        run(command, out, args.dry_run, f"extract:{name}")
        run([sys.executable, "tools/verify_bulk.py", str(archive), str(index_path),
             str(manifest), "--out", str(out / "verification.tsv")],
            out, args.dry_run, f"verify:{name}")


def audio(source: Path, out: Path, args):
    target = out / "extracted" / "audio-awc"
    if target.exists() and args.resume:
        print(f"= audio output exists: {target} (resume; use --force to rebuild)")
        return
    guard(target, args.force, False, "audio-awc output", args.dry_run)
    command = ["bash", "tools/rebuild_audio.sh", str(source / ARCHIVES["audio"]),
               str(out / "extracted")]
    run(command, out, args.dry_run, "audio")


def pilot(source: Path, out: Path, args):
    target = out / "extraction-index-pilot"
    guard(target, args.force, True, "pilot output", args.dry_run)
    run([sys.executable, "tools/extraction_index_pilot.py",
         "--output", str(target / "index.html")],
        out, args.dry_run, "pilot")


def verify(source: Path, out: Path, args):
    archives = source_map(source)
    if not args.dry_run:
        (out / "verification.tsv").unlink(missing_ok=True)
    names = [name for name in EXTRACTED
             if (out / f"extracted/{name}/manifest.tsv").is_file()
             or args.dry_run]
    for name in names:
        index_path = out / "index" / f"{name}.tsv"
        manifest = out / "extracted" / name / "manifest.tsv"
        if not args.dry_run and (not index_path.is_file() or not manifest.is_file()):
            raise SystemExit(f"missing verification input for {name}")
        run([sys.executable, "tools/verify_bulk.py", str(archives[name]),
             str(index_path), str(manifest), "--out", str(out / "verification.tsv")],
            out, args.dry_run, f"verify:{name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--output", type=Path, default=ROOT / "output")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int, default=16)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("index", "extract", "audio", "pilot", "verify", "all"):
        sub.add_parser(name)
    extract_parser = sub.choices["extract"]
    extract_parser.add_argument("--archives", nargs="+", choices=EXTRACTED,
                                default=list(EXTRACTED))
    args = ap.parse_args()
    if not hasattr(args, "archives"):
        args.archives = list(EXTRACTED)

    if args.force and args.resume:
        ap.error("--force and --resume are mutually exclusive")
    source = args.source.resolve()
    out = args.output.resolve()
    if args.command == "all":
        guard(out / "extracted", args.force, args.resume, "output/extracted", args.dry_run)
        index(source, out, args)
        extract(source, out, args)
        audio(source, out, args)
        pilot(source, out, args)
        verify(source, out, args)
    elif args.command == "index":
        index(source, out, args)
    elif args.command == "extract":
        extract(source, out, args)
    elif args.command == "audio":
        audio(source, out, args)
    elif args.command == "pilot":
        pilot(source, out, args)
    elif args.command == "verify":
        verify(source, out, args)


if __name__ == "__main__":
    main()
