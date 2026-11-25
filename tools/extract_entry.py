#!/usr/bin/env python3
"""General extraction entry point over the Rust range extractor."""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--kind", choices=("zlib", "raw", "psin"), required=True)
    parser.add_argument("--start", type=lambda value: int(value, 0), required=True)
    parser.add_argument("--end", type=lambda value: int(value, 0))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cli", type=Path, default=Path("target/debug/rage-tools-vi"))
    parser.add_argument("--log", type=Path, default=Path("output/extraction-log.jsonl"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.kind in ("zlib", "raw") and args.end is None:
        parser.error("--end is required for zlib/raw")
    if not args.cli.is_file():
        parser.error(f"CLI not found: {args.cli}")

    if args.kind == "psin":
        command = [str(args.cli), "extract", str(args.archive), f"{args.start:x}", str(args.output)]
        stored = None
    else:
        command = [
            str(args.cli), "extract-zlib" if args.kind == "zlib" else "extract-raw",
            str(args.archive), f"{args.start:x}", f"{args.end:x}", str(args.output),
        ]
        stored = args.end - args.start

    print(" ".join(command))
    if args.dry_run:
        return
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or f"extractor exited {result.returncode}")
    if not args.output.is_file():
        raise SystemExit(f"extractor produced no output: {args.output}")
    payload = args.output.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    record = {
        "time": datetime.now(timezone.utc).isoformat(),
        "archive": str(args.archive),
        "kind": args.kind,
        "start": f"0x{args.start:x}",
        "end": f"0x{args.end:x}" if args.end is not None else None,
        "output": str(args.output),
        "stored_bytes": stored,
        "decoded_bytes": len(payload),
        "sha256": digest,
        "cli": result.stdout.strip(),
    }
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    print(f"wrote {args.output} ({len(payload)} bytes) sha256={digest}")


if __name__ == "__main__":
    main()
