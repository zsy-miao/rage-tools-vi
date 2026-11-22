"""Index the Bink2 movies inside `movies.rpf`.

`movies.rpf` is 8.8 GB that the stream index leaves as one `unclassified` span: the
payload is raw video, not compressed streams, so the partitioner has nothing to
recognise. The containers are still self-describing.

A Bink2 header is:

```
+0x00  'KB2'            magic
+0x03  u8               version letter ('n', 'i', ...)
+0x04  u32              payload size in bytes
+0x08  u32              frame count
+0x0c  u32              largest frame size
+0x10  u32              frame count (again)
+0x14  u32              width
+0x18  u32              height
+0x1c  u32              frames per second
       ...
```

and the container occupies `align(0x800, payload size)` — verified against the
distance to the next movie in every case measured. Validation is the width/height/fps
triple: random `KB2` bytes inside video data do not produce 2560x1440 at 30 fps.

    python3 tools/bink_index.py /path/movies.rpf --out output/index/movies-bink.tsv
"""

import argparse
import struct
import sys
from pathlib import Path

ALIGN = 0x800
CHUNK = 1 << 26
SCAN_ALIGN = 4


def find_candidates(path, limit=0):
    offsets = []
    with path.open("rb") as handle:
        position = 0
        carry = b""
        while True:
            block = handle.read(CHUNK)
            if not block:
                break
            data = carry + block
            start = 0
            while True:
                index = data.find(b"KB2", start)
                if index < 0:
                    break
                absolute = position - len(carry) + index
                if absolute % SCAN_ALIGN == 0:
                    offsets.append(absolute)
                    if limit and len(offsets) >= limit:
                        return offsets
                start = index + 1
            carry = data[-8:]
            position += len(block)
    return offsets


def movie_at(handle, offset, file_size):
    """(end, header fields, error) for a Bink2 container at `offset`."""
    handle.seek(offset)
    head = handle.read(0x20)
    if len(head) < 0x20 or head[:3] != b"KB2":
        return None, None, "no magic"
    version = head[3]
    if not 32 <= version < 127:
        return None, None, "bad version byte"
    payload, frames, largest, frames2, width, height, fps = struct.unpack_from(
        "<7I", head, 4)
    if not (64 <= width <= 8192 and 64 <= height <= 8192):
        return None, None, "implausible dimensions"
    if not 1 <= fps <= 240:
        return None, None, "implausible frame rate"
    if payload == 0 or offset + payload > file_size:
        return None, None, "payload out of range"
    end = offset + ((payload + ALIGN - 1) // ALIGN) * ALIGN
    return min(end, file_size), {
        "version": chr(version), "payload": payload, "frames": frames,
        "width": width, "height": height, "fps": fps,
    }, None


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    if not args.archive.is_file():
        sys.exit(f"missing {args.archive}")
    size = args.archive.stat().st_size
    candidates = find_candidates(args.archive, args.limit)
    rows = []
    errors = {}
    with args.archive.open("rb") as handle:
        for offset in candidates:
            end, fields, error = movie_at(handle, offset, size)
            if error:
                errors[error] = errors.get(error, 0) + 1
                continue
            # keep only forward, non-overlapping containers
            if rows and offset < rows[-1][1]:
                continue
            rows.append((offset, end, fields))

    covered = sum(end - start for start, end, _f in rows)
    frames = sum(f["frames"] for _s, _e, f in rows)
    print(f"{args.archive.name}: {size:,} B, candidates {len(candidates):,}, "
          f"movies {len(rows):,}")
    print(f"  covered {covered:,} B ({covered / size:.3%})  frames {frames:,}")
    if errors:
        for key, value in sorted(errors.items(), key=lambda item: -item[1]):
            print(f"  rejected: {key} x{value}")
    resolutions = {}
    for _s, _e, f in rows:
        key = f"{f['width']}x{f['height']}"
        resolutions[key] = resolutions.get(key, 0) + 1
    print("  resolutions:", ", ".join(f"{k}={v}" for k, v in
                                      sorted(resolutions.items(), key=lambda i: -i[1])[:5]))
    if args.show:
        for start, end, f in rows[:5]:
            print(f"  movie +0x{start:x}..0x{end:x} ({end - start:,} B) "
                  f"'{f['version']}' {f['width']}x{f['height']} {f['fps']}fps "
                  f"{f['frames']} frames")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w") as handle:
            handle.write("kind\tstart\tend\tstored_bytes\tdecoded_bytes\tchain_start\n")
            for start, end, _f in rows:
                handle.write(f"bink\t0x{start:x}\t0x{end:x}\t{end - start}\t\t\n")
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
