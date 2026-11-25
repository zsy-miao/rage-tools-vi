"""Build the Xodus xgameruntime into `cache/shims` so the image talks to a real GDK layer.

The image resolves `xgameruntime.dll` at runtime and caches the API objects it gets back
from `QueryApiImpl`. Our own stub answers every slot with zeros, so the game's configuration
and title state are empty and it stops early. Xodus's runtime (the continuation of WineGDK)
implements the gaming runtime, XUser and the task queues for real; built as a win64 DLL with
mingw it drops straight into the staged run directory, where `tools/run_dir.py` prefers
`cache/shims/` over `cache/stubs/`.

    python3 tools/xgameruntime.py                # clone if needed, build, install
    python3 tools/xgameruntime.py --rebuild      # rebuild from the existing checkout
    python3 tools/xgameruntime.py --check        # only report whether the shim is installed

The upstream header uses `thread_local` in C, which mingw's gcc 13 accepts only through
`_Thread_local`; the configure step passes that define. Nothing else is patched.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKOUT = ROOT / "cache/xodus"
URL = "https://github.com/xodus-gaming/xgameruntime"
SHIMS = ROOT / "cache/shims"
NAME = "xgameruntime.dll"
PROXY_NAME = "xgameruntime_real.dll"
EXPORTS = ("QueryApiImpl", "InitializeApiImpl", "InitializeApiImplEx", "InitializeApiImplEx2",
           "UninitializeApiImpl", "XErrorReport")


def run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        raise SystemExit(f"{' '.join(map(str, command))}\n{result.stdout[-800:]}\n"
                         f"{result.stderr[-800:]}")
    return result.stdout


def installed():
    path = SHIMS / NAME
    return path if path.is_file() else None


PATCH = ROOT / "tools/patches/xodus-platform.patch"


def apply_patch():
    """Apply the platform patch: XSystem and XGame answer instead of refusing, and unknown
    classes can be handed back as numbered slots when XGAMERUNTIME_PROBE is set."""
    if not PATCH.is_file():
        return
    applied = subprocess.run(["git", "apply", "--reverse", "--check", str(PATCH)],
                             cwd=CHECKOUT, capture_output=True, text=True)
    if applied.returncode == 0:
        return
    result = subprocess.run(["git", "apply", str(PATCH)], cwd=CHECKOUT,
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"could not apply {PATCH}:\n{result.stderr[-600:]}")


def build(rebuild=False):
    if not CHECKOUT.is_dir():
        CHECKOUT.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", "--depth", "1", URL, str(CHECKOUT)])
    elif not rebuild and installed() is not None:
        return installed()
    apply_patch()
    preset = ["--preset", "win64", "-DCMAKE_C_FLAGS=-Dthread_local=_Thread_local"]
    if rebuild or not (CHECKOUT / "build/windows-x64").is_dir():
        run(["cmake", *preset], cwd=CHECKOUT)
    run(["cmake", "--build", "build/windows-x64"], cwd=CHECKOUT)
    built = CHECKOUT / "build/windows-x64/bin" / NAME
    if not built.is_file():
        raise SystemExit(f"no {NAME} in {built.parent}")
    SHIMS.mkdir(parents=True, exist_ok=True)
    # The runtime must keep its own name: it loads "xgameruntime.dll" by name to reach the
    # API implementations, so a proxy under that name recurses into itself.
    shutil.copy2(built, SHIMS / NAME)
    return SHIMS / NAME


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        path = installed()
        print(f"{path} {path.stat().st_size:,} B" if path else f"{SHIMS / NAME} not installed")
        return 0 if path else 1
    for tool in ("cmake", "ninja", "x86_64-w64-mingw32-gcc", "x86_64-w64-mingw32-widl"):
        if not shutil.which(tool):
            print(f"skipped ({tool} missing)")
            return 0
    path = build(args.rebuild)

    exports = subprocess.run(["x86_64-w64-mingw32-objdump", "-p", str(path)],
                             capture_output=True, text=True).stdout
    missing = [name for name in EXPORTS if name not in exports]
    print(f"{path} {path.stat().st_size:,} B, "
          f"{len(EXPORTS) - len(missing)}/{len(EXPORTS)} entry points"
          + (f", missing {missing}" if missing else ""))
    print("staged by tools/run_dir.py: it prefers cache/shims over cache/stubs")
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
