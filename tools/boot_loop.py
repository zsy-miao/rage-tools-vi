"""Iterate the console image's guard asserts: patch one, run, find the next.

The image stops at `swi(3)` sites that follow a failed initialisation call. Each stop names
one expectation of the platform. Patching that byte in a copy turns the stop into the next
line of the log, so the loop measures the whole chain instead of one stop at a time.

A stop that is not `0x80000003` inside `game.exe` ends the loop: an access violation is a
real fault, not a guard, and patching it would hide the cause.

    python3 tools/boot_loop.py --game-dir <dump> --rounds 12
"""

import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from rage import proton_wine  # noqa: E402
from patch_guard import rva_to_offset  # noqa: E402
from run_dir import stage  # noqa: E402

BREAKPOINT = "0x80000003"


def image_base(exe_name, wait=8.0):
    """Load base of the image as the running process mapped it, read from /proc.

    The log's backtrace lines are not always emitted, so the base is taken from the
    process itself: the lowest `maps` entry whose path ends with the executable name.
    """
    import time
    deadline = time.time() + wait
    while time.time() < deadline:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                command = (entry / "cmdline").read_bytes().decode("utf-8", "replace")
            except OSError:
                continue
            if exe_name not in command.replace("\x00", " "):
                continue
            try:
                maps = (entry / "maps").read_text()
            except OSError:
                continue
            bases = []
            for line in maps.splitlines():
                parts = line.split()
                if len(parts) >= 6 and parts[5].endswith(exe_name):
                    bases.append(int(parts[0].split("-")[0], 16))
            if bases:
                return min(bases)
        import time as _t
        _t.sleep(0.05)
    return None


def run_round(exe, game_dir, stubs, log_path, timeout):
    wine = proton_wine()
    if wine is None:
        raise SystemExit("no Proton wine found; set PROTON_WINE")
    # Measured: an explicit native override for these names makes Wine skip them, so the
    # stubs are left to load from the game directory on their own (verified with +loaddll).
    env = dict(os.environ, WINEPREFIX=os.environ.get("PROTON_PREFIX",
                                                    str(Path.home() / ".proton-vi/pfx")),
               STUB_TRACE="1", WINEDEBUG="+seh")
    with open(log_path, "w") as sink:
        process = subprocess.Popen([str(wine), str(exe)], cwd=str(game_dir), env=env,
                                   stdout=sink, stderr=subprocess.STDOUT)
        base = image_base(exe.name)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise
    log = log_path.read_text()
    return process.returncode, log, base


def stop_of(log):
    """(exception code, fault address) of the last unhandled stop in the log."""
    lines = log.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        match = re.search(r"Unhandled exception 0x([0-9a-fA-F]+) in thread [0-9a-fA-F]+ at address ([0-9a-fA-F]+)",
                          lines[index])
        if not match:
            continue
        return match.group(1), int(match.group(2), 16)
    return None, None


def handled_breakpoint(log):
    """(code, address) of the last handled `int3` the image's own handler caught.

    Once the image registers its crash reporter it *handles* the guard's breakpoint instead
    of letting it go unhandled, and the process then exits quietly. The stop is the same
    instruction, so it is read from the dispatch line and its `rip`, which names the `int3`
    itself (the `addr` field is one past it).
    """
    lines = log.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        match = re.search(r"dispatch_exception code=(80000003) .*addr=([0-9a-fA-F]+)", lines[index])
        if not match:
            continue
        for follower in lines[index:index + 4]:
            found = re.search(r"dispatch_exception rip=([0-9a-fA-F]+)", follower)
            if found:
                return match.group(1), int(found.group(1), 16)
        return match.group(1), int(match.group(2), 16)
    return None, None


def stop_in(log):
    """(code, address) of the stop, unhandled first, then a handled breakpoint."""
    code, address = stop_of(log)
    if code is not None:
        return code, address
    return handled_breakpoint(log)


def next_guard(log):
    """(rva or None, exception code, address) for the *unhandled* stop in the log.

    The log also carries handled exceptions, including the debug-print exception the image
    raises for every trace line, so only the block that follows "Unhandled exception"
    counts.
    """
    lines = log.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        match = re.search(r"Unhandled exception 0x([0-9a-fA-F]+) in thread [0-9a-fA-F]+ at address ([0-9a-fA-F]+)",
                          lines[index])
        if not match:
            continue
        code = match.group(1)
        address = int(match.group(2), 16)
        rip = None
        base = None
        for line in reversed(lines[:index]):
            if rip is None:
                found = re.search(r"dispatch_exception rip=([0-9a-f]+)", line)
                if found:
                    rip = int(found.group(1), 16)
                    continue
            found = re.search(r'virtual_unwind backtrace: ([0-9A-F]+): L"game\.exe" \+ ([0-9A-F]+)', line)
            if found:
                base = int(found.group(1), 16) - int(found.group(2), 16)
                break
        if rip is None or base is None:
            return None, code, address
        return rip - base, code, address
    return None, None, None


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--exe", type=Path, default=ROOT / "cache/exe/game_scarlett_master.exe")
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--start", type=Path,
                        help="start from this image instead of --exe (already patched)")
    parser.add_argument("--base", type=lambda v: int(v, 0), default=0x6FFFF2F50000,
                        help="load base of the image; Wine mapped it there in every run here")
    args = parser.parse_args()

    stubs = ROOT / "cache/stubs"
    build = subprocess.run([sys.executable, str(ROOT / "tools/stub_dlls.py"),
                            str(args.exe), "--out", str(stubs)],
                           capture_output=True, text=True)
    if build.returncode != 0:
        print(build.stdout[-400:], build.stderr[-400:])
        return 1
    print(f"stub DLLs: {len(list(stubs.glob('*.dll')))}")
    run_dir, links, placed = stage(args.game_dir, ROOT / "cache/run", stubs)
    print(f"run directory: {run_dir} ({links} linked, {placed} stubs); the dump is not written")
    args.game_dir = run_dir

    original = bytearray((args.start or args.exe).read_bytes())
    patches = []
    keep = ROOT / "cache/boot-patched.exe"
    try:
        return _loop(args, stubs, original, patches, keep)
    finally:
        pass


def _loop(args, stubs, original, patches, keep):
    work = Path(tempfile.mkdtemp(prefix="bootloop-"))
    exe = args.game_dir / "bootloop.exe"
    exe.write_bytes(original)
    log_path = work / "run.log"

    for round_index in range(1, args.rounds + 1):
        rva, code, address = (None, None, None)
        try:
            returncode, log, base_hint = run_round(exe, args.game_dir, stubs, log_path, args.timeout)
        except subprocess.TimeoutExpired:
            print(f"round {round_index}: still running at {args.timeout}s — no stop")
            shutil.copy(log_path, ROOT / "cache/boot-loop.log")
            keep.write_bytes(exe.read_bytes())
            exe.unlink(missing_ok=True)
            return 0
        code, address = stop_in(log)
        # The /proc base is only a hint: Wine may have mapped the image elsewhere by the
        # time the process is gone. The declared base is authoritative unless the address
        # does not fall inside the image at all.
        base = args.base
        if address is not None and not (base <= address < base + 0x72A0000) and base_hint:
            base = base_hint
        rva = address - base if address is not None else None
        if rva is not None and not (0 <= rva < 0x5F3F966):
            rva = None
        if code is None:
            print(f"round {round_index}: no stop found (exit {returncode}) — loop ends")
            shutil.copy(log_path, ROOT / "cache/boot-loop.log")
            keep.write_bytes(exe.read_bytes())
            exe.unlink(missing_ok=True)
            return 2
        if code != "80000003":
            print(f"round {round_index}: stop is {code} at {address:#x} — not a guard, loop ends")
            shutil.copy(log_path, ROOT / "cache/boot-loop.log")
            keep.write_bytes(exe.read_bytes())
            exe.unlink(missing_ok=True)
            return 2
        if rva is None:
            print(f"round {round_index}: guard outside the image ({address:#x}) — loop ends")
            shutil.copy(log_path, ROOT / "cache/boot-loop.log")
            keep.write_bytes(exe.read_bytes())
            exe.unlink(missing_ok=True)
            return 2
        data = bytearray(exe.read_bytes())
        # The reported address is the instruction after the trap, so the trap itself is
        # the byte before it when it is an 0xCC.
        offset = rva_to_offset(data, rva)
        if data[offset] != 0xCC and data[offset - 1] == 0xCC:
            offset -= 1
            rva -= 1
        data[offset] = 0x90
        exe.write_bytes(data)
        patches.append(rva)
        print(f"round {round_index}: guard at image+{rva:#x} patched "
              f"({len(patches)} total, exit was {returncode})")

    print(f"{len(patches)} guards patched: " + ", ".join(hex(rva) for rva in patches))
    # Keep the patched image: it is what the frame test boots when the goal is to see how
    # far rendering gets, and a copy in the game directory is what the stubs sit beside.
    keep.write_bytes(exe.read_bytes())
    exe.unlink(missing_ok=True)
    print(f"kept {keep}")
    shutil.copy(log_path, ROOT / "cache/boot-loop.log")
    return 0


if __name__ == "__main__":
    sys.exit(main())
