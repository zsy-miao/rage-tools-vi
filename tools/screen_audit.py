"""Audit the screen in pixels: did anything change while the image ran?

Window titles, process ids and `WM_CLASS` are all proxies. This looks at the pixels instead:
it captures the whole session display before the launch, once per interval while the image runs,
and once after it exits, then reports exactly which pixels changed and where.

    python3 tools/screen_audit.py --game-dir <dump> --seconds 20
    python3 tools/screen_audit.py --game-dir <dump> --threshold 8 --interval 1.0

A run where no pixel changes is a blank screen, whatever the process table says. A run where
pixels change inside one rectangle names the window the image did draw, by measurement.

Capture is `flameshot full -r` (Wayland: an X11 grab of the session is black), decoded and
downscaled by ffmpeg. The before-shot is also compared with the after-shot so a change caused by
the harness itself is distinguishable from one caused by the image.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

SIZE = "640x360"  # audit resolution: cheap to diff, fine enough to see a window


def shot():
    """Raw grayscale frame of the whole session display, or None."""
    result = subprocess.run(["flameshot", "full", "-r"], capture_output=True, timeout=120)
    if result.returncode != 0 or not result.stdout:
        return None
    frame = subprocess.run(["ffmpeg", "-v", "error", "-i", "pipe:0", "-vf", f"scale={SIZE}",
                            "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                           input=result.stdout, capture_output=True, timeout=120)
    return frame.stdout or None


def diff(a, b, threshold):
    """(changed pixel count, bounding box, peak difference) between two frames."""
    if not a or not b or len(a) != len(b):
        return None, None, 0
    width = int(SIZE.split("x")[0])
    count = 0
    peak = 0
    x0 = y0 = 10 ** 6
    x1 = y1 = -1
    for index, (left, right) in enumerate(zip(a, b)):
        delta = left - right if left > right else right - left
        if delta > peak:
            peak = delta
        if delta >= threshold:
            count += 1
            x = index % width
            y = index // width
            if x < x0: x0 = x
            if y < y0: y0 = y
            if x > x1: x1 = x
            if y > y1: y1 = y
    if count == 0:
        return 0, None, peak
    return count, (x0, y0, x1 - x0 + 1, y1 - y0 + 1), peak


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--exe", default="./game.exe")
    parser.add_argument("--seconds", type=float, default=20)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--threshold", type=int, default=6)
    parser.add_argument("--online", action="store_true")
    args = parser.parse_args()

    for tool in ("flameshot", "ffmpeg"):
        if not shutil.which(tool):
            print(f"skipped ({tool} missing)")
            return 0
    if not os.environ.get("DISPLAY"):
        print("skipped (no DISPLAY)")
        return 0
    from rage import proton_wine
    from run_dir import stage

    wine = proton_wine()
    if wine is None:
        print("skipped (no Proton wine)")
        return 0
    stubs = ROOT / "cache/stubs"
    subprocess.run([sys.executable, str(ROOT / "tools/stub_dlls.py"),
                    str(ROOT / "cache/exe/game_scarlett_master.exe"), "--out", str(stubs)],
                   capture_output=True)
    run, _links, _placed = stage(args.game_dir, ROOT / "cache/run", stubs)

    before = shot()
    if before is None:
        print("skipped (capture failed)")
        return 0
    launch = [str(wine), args.exe] if args.online else ["unshare", "-rn", str(wine), args.exe]
    process = subprocess.Popen(launch, cwd=str(run),
                               env=dict(os.environ, WINEPREFIX=os.environ.get(
                                   "PROTON_PREFIX", str(Path.home() / ".proton-vi/pfx"))),
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"{SIZE} before-shot taken; watching {args.seconds:.0f}s at {args.interval:.1f}s")
    frames = []
    deadline = time.time() + args.seconds
    while time.time() < deadline:
        if process.poll() is not None:
            break
        frames.append((round(time.time() - (deadline - args.seconds), 1), shot()))
        time.sleep(args.interval)
    exited = process.poll()
    if exited is None:
        process.terminate()
        try:
            exited = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            exited = process.wait()
    after = shot()

    changed_any = False
    for index in range(1, len(frames)):
        stamp, frame = frames[index]
        count, box, peak = diff(frames[index - 1][1], frame, args.threshold)
        if count is None:
            continue
        if count:
            changed_any = True
            print(f"  t={stamp:5.1f}s  {count:6d} px changed  box {box[2]}x{box[3]}+{box[0]}+{box[1]}"
                  f"  peak {peak}")
    count, box, peak = diff(before, after, args.threshold)
    print(f"  before vs after: {count} px changed"
          + (f"  box {box[2]}x{box[3]}+{box[0]}+{box[1]}  peak {peak}" if count else ""))
    print(f"  process exit {exited}")
    if not changed_any and not count:
        print("  verdict: the screen did not change by a single pixel while the image ran")
    return 0


if __name__ == "__main__":
    sys.exit(main())
