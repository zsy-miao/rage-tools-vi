"""Build the d3d12_xs.dll shim that backs the console D3D12 entry points with vkd3d-proton.

The image imports three names from `d3d12_xs.dll`; the shipped Xbox library cannot run under
Wine, and a stub that returns 0 hands the image objects it cannot use. `tools/d3d12_xs.c`
implements the three, forwarding the two that have a PC counterpart to the prefix's
`d3d12.dll` (vkd3d-proton) and logging every call and the Xbox device-parameter words.

    python3 tools/d3d12_shim.py                    # build into cache/shims
    python3 tools/d3d12_shim.py --check             # fail if the build is stale

`tools/run_dir.py` prefers `cache/shims/<name>.dll` over `cache/stubs/<name>.dll`, so a
staged run picks this up without any other change.
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools/d3d12_xs.c"
OUT = ROOT / "cache/shims"
NAME = "d3d12_xs.dll"
MINGW = "x86_64-w64-mingw32-gcc"

EXPORTS = ("D3D12ConfigureVirtualMemoryX", "D3D12SerializeVersionedRootSignature",
           "D3D12XboxCreateDevice")


def build(out=OUT, force=True):
    out.mkdir(parents=True, exist_ok=True)
    target = out / NAME
    if not force and target.is_file() and target.stat().st_mtime >= SOURCE.stat().st_mtime:
        return target
    command = [MINGW, "-shared", "-O2", "-Wall", "-Wno-cast-function-type",
               "-o", str(target), str(SOURCE), "-lkernel32"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(result.stderr[-1000:])
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--check", action="store_true", help="verify the build is current")
    args = parser.parse_args()
    target = build(args.out, force=not args.check)
    exports = subprocess.run(["x86_64-w64-mingw32-objdump", "-p", str(target)],
                             capture_output=True, text=True).stdout
    missing = [name for name in EXPORTS if name not in exports]
    print(f"{target} {target.stat().st_size} B, "
          f"{len(EXPORTS) - len(missing)}/{len(EXPORTS)} exports"
          + (f", missing {missing}" if missing else ""))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
