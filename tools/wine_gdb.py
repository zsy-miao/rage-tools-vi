"""Attach gdb to the running console image and stop at image addresses.

Wine's own breakpoint handling makes `catch signal SIGTRAP` useless, the loader is 32-bit
until it execs the 64-bit preloader (so gdb picks i386 and mangles addresses), and ptrace
scope is 1 on this machine. What works is to start the image inside a user namespace — which
grants `CAP_SYS_PTRACE` for that namespace — find the process whose `exe` is `wine64*`, attach
to it, force the architecture, and set software breakpoints at absolute addresses.

    python3 tools/wine_gdb.py --game-dir <dump> --at 0x2237178
    python3 tools/wine_gdb.py --game-dir <dump> --at 0x2236e73,0x2237167 --single

`--at` takes image RVAs; the tool adds the load base it measured (`0x6FFFF2F50000`). Each
breakpoint prints the registers named by `--registers` and a short backtrace, then continues.
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

BASE = 0x6FFFF2F50000


def gdb_script(addresses, registers, single):
    lines = ["set pagination off", "set confirm off"]
    for index, address in enumerate(addresses, start=1):
        lines.append(f"break *{address:#x}")
    for index, address in enumerate(addresses, start=1):
        lines.append(f"commands {index}")
        lines.append("  silent")
        shown = ", ".join(f"{name}=%#lx" for name in registers)
        args = ", ".join(f"${name}" for name in registers)
        lines.append(f'  printf "HIT {address:#x} {shown}\\n", {args}')
        lines.append("  bt 4")
        lines.append("  quit" if single else "  continue")
        lines.append("end")
    lines.append("continue")
    lines.append('printf "END-OF-RUN\\n"')
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--exe", type=Path, default=ROOT / "cache/exe/game_scarlett_master.exe")
    parser.add_argument("--at", required=True, help="image RVAs, comma separated")
    parser.add_argument("--registers", default="rcx,rdx,rsi,rax",
                        help="registers to print at each stop")
    parser.add_argument("--single", action="store_true", help="stop at the first hit")
    parser.add_argument("--delay", type=float, default=0.0, help="seconds before attaching")
    parser.add_argument("--base", type=lambda v: int(v, 0), default=BASE)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    from rage import proton_wine
    from run_dir import stage
    wine = proton_wine()
    if wine is None:
        print("skipped (no Proton wine; set PROTON_WINE)")
        return 0
    stubs = ROOT / "cache/stubs"
    subprocess.run([sys.executable, str(ROOT / "tools/stub_dlls.py"), str(args.exe),
                    "--out", str(stubs)], capture_output=True)
    run, _links, _placed = stage(args.game_dir, ROOT / "cache/run", stubs)
    addresses = [args.base + int(value, 0) for value in args.at.split(",")]
    script = Path(tempfile.mkdtemp(prefix="winegdb-")) / "commands.gdb"
    script.write_text(gdb_script(addresses, args.registers.split(","), args.single))

    inner = f'''
      cd "{run}"
      "{wine}" ./game.exe >/tmp/wine-gdb-run.log 2>&1 &
      sleep {args.delay}
      for i in $(seq 1 200); do
        for candidate in $(pgrep -f "game.exe" 2>/dev/null); do
          case "$(readlink /proc/$candidate/exe 2>/dev/null)" in *wine64*) pid=$candidate;; esac
        done
        [ -n "${{pid:-}}" ] && break; sleep 0.05
      done
      echo "attached to ${{pid:-nothing}}"
      [ -n "${{pid:-}}" ] && gdb -q -batch -p "$pid" \\
          -ex "set architecture i386:x86-64" -x "{script}"
      wait
    '''
    env = dict(os.environ, WINEPREFIX=os.environ.get("PROTON_PREFIX",
                                                     str(Path.home() / ".proton-vi/pfx")),
               WINEDEBUG="-all", STUB_TRACE="-")
    result = subprocess.run(["unshare", "-r", "bash", "-c", inner], env=env, text=True,
                            capture_output=True, timeout=args.timeout)
    output = result.stdout + result.stderr
    for line in output.splitlines():
        if any(token in line for token in ("attached", "HIT", "END-OF-RUN", "#0", "#1", "#2",
                                           "#3", "Cannot", "No such", "not in executable")):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
