"""Stage a game directory so a run never writes into the dump.

The console image needs its stub DLLs *beside* the executable, and the previous launchers
copied them straight into the dump — which overwrote the package's own console DLLs
(`d3d12_xs.dll`, `xg_xs.dll`, `xmem.dll`, ... and twelve more). Those are shipped Xbox
binaries; once replaced by a 231 KiB stub they cannot be read back, and nothing else on the
machine holds a copy.

So the run gets a directory of its own: every package entry is symlinked (reads only), and
the stub DLLs are the only real files, placed under the same names. The package stays
untouched, and a re-run only refreshes the stubs.

    python3 tools/run_dir.py --game-dir <dump>          # stage into cache/run, print it
    python3 tools/run_dir.py --game-dir <dump> --out cache/run

`stage()` is the function the other launchers call.
"""

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "cache/run"
DEFAULT_STUBS = ROOT / "cache/stubs"
DEFAULT_SHIMS = ROOT / "cache/shims"


def stage(game_dir, out=DEFAULT_OUT, stubs=DEFAULT_STUBS, shims=DEFAULT_SHIMS):
    """(re)build `out` as a read-only symlink view of `game_dir` plus the stub DLLs.

    A real implementation in `shims` (for example the d3d12_xs proxy built from
    `tools/d3d12_xs.c`) wins over the stub of the same name.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    provided = {}
    for directory in (Path(stubs), Path(shims)):
        if directory.is_dir():
            provided.update({path.name.lower(): path for path in directory.glob("*.dll")})
    stub = provided
    links = 0
    placed = 0
    wanted = set()
    for entry in sorted(Path(game_dir).iterdir()):
        wanted.add(entry.name)
        target = out / entry.name
        if target.is_symlink() or target.exists():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()
        if entry.name.lower() in stub:
            shutil.copy2(stub[entry.name.lower()], target)
            placed += 1
        else:
            target.symlink_to(entry.resolve())
            links += 1
    for stale in sorted(out.iterdir()):
        if stale.name not in wanted:
            if stale.is_dir() and not stale.is_symlink():
                shutil.rmtree(stale)
            else:
                stale.unlink()
    return out, links, placed


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--stubs", type=Path, default=DEFAULT_STUBS)
    args = parser.parse_args()
    if not args.game_dir.is_dir():
        print(f"skipped (no game directory at {args.game_dir})")
        return 0
    if not any(args.stubs.glob("*.dll")):
        print(f"skipped (no stubs in {args.stubs}; run tools/stub_dlls.py first)")
        return 0
    out, links, placed = stage(args.game_dir, args.out, args.stubs)
    print(f"{out}: {links} entries linked, {placed} stub DLLs placed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
