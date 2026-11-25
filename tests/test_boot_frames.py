"""Acceptance test: the console image opens a window and reaches the menu.

This is the scoreboard for "the game runs", and it is deliberately literal: on the
session's own display the image must open a real window, draw into it, and settle into a
static, content-bearing screen after the attract videos — the menu. Nothing here runs on a
hidden virtual display, and nothing here steals focus, because a window nobody can see is
not the thing being asked for.

What is measured, about once per second, from that window's rectangle only:
  * window   — a mapped top-level X window appears after launch and belongs to the game
               (pid match first, then the image's name in the title);
  * content  — grayscale spread and the share of pixels above a quarter of full scale.
               A pointer cursor gives contrast but ~0 % lit, so `lit` decides;
  * motion   — mean absolute difference against the previous frame. Videos move; a menu
               does not, so `--settle` seconds of low-motion content frames is what counts
               as "dropped into the menu";
  * identity — after the process exits, the same rectangle must change. If it still shows
               what was scored, that content was never the game's;
  * answer   — once the picture settles (the menu, after the attract videos) the harness clicks
               it and requires the picture to change. A menu that ignores input has not been
               reached: the pass is video -> menu -> "we are here".

Capture: Wine's windows are X11 (XWayland on a Wayland session). A plain `x11grab` of a
Wayland session reads a black framebuffer, so on Wayland the screen is captured through
`flameshot` and cropped to the window rectangle; with only X11, `ffmpeg` grabs the window
rectangle directly. `--capture` forces either. The rectangle must stay unobstructed while
the run lasts — this test cannot see what a compositor draws on top, so keep other windows
off it, and it will say so if the window is minimized.

The image's crash reporter posts a minidump to the publisher's Backtrace project for every
fault it catches, so the run is started inside a network namespace with no route
(`unshare -rn`); `--online` lifts that. Prerequisites, all skipped rather than failed when
missing:
  * a session display (`DISPLAY`), the image (`cache/exe/game_scarlett_master.exe`),
  * a game directory with the package (`--game-dir` or `RAGE_GAME_DIR`),
  * Proton's wine (`PROTON_WINE` or a Steam/GE installation),
  * `ffmpeg`, `xwininfo`, `xprop`, and `flameshot` when the session is Wayland.

    python3 tests/test_boot_frames.py --game-dir <dump>
    python3 tests/test_boot_frames.py --selftest    # prove the harness can pass
    python3 tests/test_boot_frames.py --game-dir <dump> --seconds 900 --settle 5

The image is launched unpatched, so the run stops where the shipped executable stops.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

FAILED = []
WIDTH, HEIGHT = 320, 180  # scoring resolution; the crop is downscaled before reading


def check(name, condition, detail=""):
    print(f"  {'ok  ' if condition else 'FAIL'}  {name} {detail}")
    if not condition:
        FAILED.append(name)
    return condition


def windows():
    """{window id: (title, width, height, x, y)} for the top-level windows of the display."""
    result = subprocess.run(["xwininfo", "-root", "-children"], capture_output=True, text=True)
    found = {}
    line_re = re.compile(r'^\s*(0x[0-9a-f]+)\s+(?:"([^"]*)"|\(has no name\)):\s*\([^)]*\)\s+'
                         r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)\s+\+(-?\d+)\+(-?\d+)')
    for line in result.stdout.splitlines():
        match = line_re.match(line)
        if match:
            found[match.group(1)] = (match.group(2) or "", int(match.group(3)),
                                     int(match.group(4)), int(match.group(7)),
                                     int(match.group(8)))
    return found


def rectangle(window):
    """(x, y, width, height) of a window in root coordinates, or None."""
    result = subprocess.run(["xwininfo", "-id", window], capture_output=True, text=True)
    found = {}
    for key in ("Absolute upper-left X", "Absolute upper-left Y", "Width", "Height"):
        match = re.search(rf"^\s*{key}:\s+(-?\d+)", result.stdout, re.MULTILINE)
        if match is None:
            return None
        found[key] = int(match.group(1))
    if "Map State: IsViewable" not in result.stdout:
        return None
    return (found["Absolute upper-left X"], found["Absolute upper-left Y"],
            found["Width"], found["Height"])


def minimize_state(window):
    """'hidden', 'normal', or 'unknown' when the property cannot be read."""
    result = subprocess.run(["xprop", "-id", window, "_NET_WM_STATE"], capture_output=True,
                            text=True)
    if result.returncode != 0:
        return "unknown"
    if "_NET_WM_STATE_HIDDEN" in result.stdout:
        return "hidden"
    return "normal"


def window_classes(window):
    """Lower-case WM_CLASS values of a window and its children.

    On a Wayland session the compositor wraps each client in a frame window: the frame
    carries the title and a _NET_WM_PID that belongs to the compositor, while the client
    inside it carries the class. Both are read so a window can still be attributed.
    """
    names = set()
    ids = [window]
    tree = subprocess.run(["xwininfo", "-id", window, "-children"], capture_output=True,
                          text=True).stdout
    ids += re.findall(r"^\s+(0x[0-9a-f]+)", tree, re.MULTILINE)
    for candidate in ids:
        result = subprocess.run(["xprop", "-id", candidate, "WM_CLASS"], capture_output=True,
                                text=True)
        names.update(name.lower() for name in re.findall(r'"([^"]*)"', result.stdout))
    return names


def window_pid(window):
    result = subprocess.run(["xprop", "-id", window, "_NET_WM_PID"], capture_output=True,
                            text=True)
    match = re.search(r"=\s*(\d+)", result.stdout)
    return int(match.group(1)) if match else None


def descendants(pid):
    """That pid and every live child of it, so a window owned by a helper still matches."""
    seen = {pid}
    pending = [pid]
    while pending:
        out = subprocess.run(["pgrep", "-P", str(pending.pop())], capture_output=True,
                             text=True).stdout
        for line in out.split():
            child = int(line)
            if child not in seen:
                seen.add(child)
                pending.append(child)
    return seen


def new_windows(before):
    """Windows that appeared since `before`, with a plausible size: [(id, title, w, h)]."""
    return [(window, title, width, height)
            for window, (title, width, height, _x, _y) in windows().items()
            if window not in before and width >= 320 and height >= 240]


def pick_window(before, pids, names):
    """The game's window among the new ones, or None.

    A window is attributed only by something the client itself set — its process id (a
    plain X session), its title, or its class. A merely new, large window is not enough:
    that could be the operator's, and counting it would be a false pass.
    """
    candidates = new_windows(before)
    for window, _title, _width, _height in candidates:
        if window_pid(window) in pids:
            return window
    for window, title, _width, _height in candidates:
        if any(name in title.lower() for name in names):
            return window
    for window, _title, _width, _height in candidates:
        classes = window_classes(window)
        if any(name in cls for name in names for cls in classes):
            return window
    return None


def capture(method, screen, rect, display):
    """One PNG (desktop) or raw frame of the window rectangle; (frame, error)."""
    x, y, width, height = rect
    if x < 0 or y < 0 or x + width > screen[0] or y + height > screen[1]:
        return None, f"rectangle {rect} leaves the {screen[0]}x{screen[1]} screen"
    crop = f"crop={width}:{height}:{x}:{y},scale={WIDTH}:{HEIGHT}"
    if method == "desktop":
        shot = subprocess.run(["flameshot", "full", "-r"], capture_output=True, timeout=120)
        if shot.returncode != 0 or not shot.stdout:
            return None, (shot.stderr.decode(errors="replace").strip().splitlines() or
                          ["flameshot produced no image"])[-1]
        source = ["-i", "pipe:0"]
        payload = shot.stdout
    else:
        source = ["-f", "x11grab", "-video_size", f"{width}x{height}",
                  "-i", f"{display}+{x},{y}"]
        payload = b""
    result = subprocess.run(["ffmpeg", "-v", "error", *source, "-frames:v", "1", "-vf", crop,
                             "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                            input=payload or None, capture_output=True, timeout=120)
    if result.returncode != 0 or not result.stdout:
        tail = result.stderr.decode(errors="replace").strip().splitlines()
        return None, (tail or ["ffmpeg produced no frame"])[-1]
    return result.stdout, ""


def spread(frame):
    """(contrast, deviation, lit fraction) of a grayscale frame."""
    if not frame:
        return 0, 0.0, 0.0
    low, high = min(frame), max(frame)
    mean = sum(frame) / len(frame)
    variance = sum((value - mean) ** 2 for value in frame) / len(frame)
    lit = sum(1 for value in frame if value > 64) / len(frame)
    return high - low, variance ** 0.5, lit


def motion(previous, frame):
    """Mean absolute difference from the previous frame, 255.0 when the shape changed."""
    if not previous or not frame or len(previous) != len(frame):
        return 255.0
    return sum(abs(a - b) for a, b in zip(previous, frame)) / len(frame)


def selftest(args, method, display, screen):
    """The same detection, capture and scoring, pointed at a program that does open a window.

    A scoreboard that has never recorded a pass is not evidence of anything: this runs Wine's
    notepad, and if the window is not found, cropped and scored as carrying content, the
    harness is what is broken — not the image.
    """
    from rage import proton_wine
    wine = proton_wine()
    if wine is None:
        print("  skipped (no Proton wine)")
        return 0
    before = windows()
    env = dict(os.environ, WINEPREFIX=os.environ.get("PROTON_PREFIX",
                                                     str(Path.home() / ".proton-vi/pfx")))
    launch = ["unshare", "-rn", str(wine), "notepad"] if not args.online else \
        [str(wine), "notepad"]
    print("  CONTROL: wine notepad, not the game (this only proves the harness works)")
    frames_dir = ROOT / "cache/frames" / ("control-" + time.strftime("%Y%m%dT%H%M%S"))
    frames_dir.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(launch, env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
    window = None
    frames = 0
    best = (0, 0.0, 0.0)
    best_splash = (0.0, None)
    try:
        deadline = time.time() + args.seconds
        while time.time() < deadline:
            if window is None:
                window = pick_window(before, descendants(process.pid), ["notepad"])
                if window is None:
                    time.sleep(0.5)
                    continue
                rect = rectangle(window)
                print(f"  window {window} at {rect[2]}x{rect[3]}+{rect[0]}+{rect[1]} "
                      f"via {method}")
            frame, error = capture(method, screen, rect, display)
            if frame is None:
                print(f"  capture failed: {error}")
                break
            contrast, deviation, lit = spread(frame)
            if (contrast, deviation, lit) > best:
                best = (contrast, deviation, lit)
            if contrast >= args.min_spread and lit >= args.min_lit:
                frames += 1
                png = frames_dir / f"{frames:03d}.png"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo",
                                "-pix_fmt", "gray", "-s", f"{WIDTH}x{HEIGHT}", "-i", "pipe:0",
                                "-frames:v", "1", str(png)], input=frame, capture_output=True)
            time.sleep(1)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    print(f"  window {window or 'none'}, content frames {frames}, contrast {best[0]}, "
          f"lit {best[2]:.1%}")
    print(f"  frames kept in {frames_dir.relative_to(ROOT)}")
    check("the harness finds a window", window is not None)
    check("the harness captures content from it", frames >= max(1, args.min_frames // 2),
          f"({frames})")
    print()
    print("PASS" if not FAILED else f"FAIL: {len(FAILED)} check(s)")
    return 0 if not FAILED else 1


def similarity(frame, reference):
    """(SSIM, PSNR) between two images, the metrics a visual-regression test uses.

    SSIM answers "is this the same picture structurally" (1.0 identical); PSNR answers "how
    far apart are the pixels in dB". Both come from ffmpeg's filters, so no extra tool is
    needed and the numbers are comparable with any other run of the same filters.
    """
    ssim = subprocess.run(["ffmpeg", "-v", "info", "-i", frame, "-i", reference,
                           "-lavfi", "ssim", "-f", "null", "-"], capture_output=True, text=True)
    psnr = subprocess.run(["ffmpeg", "-v", "info", "-i", frame, "-i", reference,
                           "-lavfi", "psnr", "-f", "null", "-"], capture_output=True, text=True)
    def value(text, tag):
        for line in text.splitlines():
            if tag in line and ":" in line:
                part = line.rsplit(":", 1)[-1].strip().split()[0]
                try:
                    return float(part)
                except ValueError:
                    return None
        return None
    return value(ssim.stderr, "SSIM"), value(psnr.stderr, "PSNR")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game-dir", type=Path,
                        default=Path(os.environ["RAGE_GAME_DIR"]) if os.environ.get("RAGE_GAME_DIR") else None)
    parser.add_argument("--exe", type=Path, default=ROOT / "cache/exe/game_scarlett_master.exe")
    parser.add_argument("--capture", choices=("auto", "x11", "desktop"), default="auto")
    parser.add_argument("--window-name", action="append", default=[], metavar="TEXT",
                        help="extra title or WM_CLASS text that identifies the image's window")
    parser.add_argument("--seconds", type=int, default=240,
                        help="how long to watch; attract videos run long before the menu")
    parser.add_argument("--min-frames", type=int, default=5)
    parser.add_argument("--min-spread", type=int, default=24)
    parser.add_argument("--min-lit", type=float, default=0.02,
                        help="share of pixels above a quarter of full scale")
    parser.add_argument("--splash", type=Path,
                        help="reference artwork the frame is compared against (default: the "
                             "package's xbs_splash.png); SSIM per kept frame, best kept")
    parser.add_argument("--min-splash-ssim", type=float, default=0.80)
    parser.add_argument("--compare-frame", metavar="FILE:REFERENCE",
                        help="visual-regression comparison of a kept frame against a "
                             "reference image, by SSIM and PSNR (ffmpeg's filters)")
    parser.add_argument("--min-ssim", type=float, default=0.99)
    parser.add_argument("--assert-pixel", metavar="FILE:X,Y=R,G,B",
                        help="assert one pixel of a saved frame, the way "
                             "tools/explorer_image_fixture.py --assert-screenshot does")
    parser.add_argument("--tolerance", type=int, default=10)
    parser.add_argument("--selftest", action="store_true",
                        help="run a known windowing program instead of the image, so a pass "
                             "proves the harness can see a window, capture it and score content")
    parser.add_argument("--online", action="store_true",
                        help="allow the image's network access (its crash reporter posts "
                             "minidumps to submit.backtrace.io); off by default")
    parser.add_argument("--click", action="store_true", default=True,
                        help="click the menu once it settles; a menu that does nothing on "
                             "input has not been reached")
    parser.add_argument("--response-seconds", type=int, default=8,
                        help="how long the menu has to react to the click")
    parser.add_argument("--settle", type=int, default=3,
                        help="consecutive content frames with motion below --max-motion")
    parser.add_argument("--max-motion", type=float, default=1.0,
                        help="mean frame difference that still counts as static, 0-255")
    args = parser.parse_args()

    if args.compare_frame:
        frame, _, reference = args.compare_frame.partition(":")
        ssim, psnr = similarity(frame, reference)
        if ssim is None:
            print(f"  FAIL  could not compare {frame} with {reference}")
            return 1
        ok = ssim >= args.min_ssim
        print(f"  {'ok  ' if ok else 'FAIL'}  SSIM {ssim:.4f} (wanted >= {args.min_ssim}), "
              f"PSNR {'n/a' if psnr is None else f'{psnr:.1f} dB'}")
        return 0 if ok else 1

    if args.assert_pixel:
        target, _, expected = args.assert_pixel.rpartition("=")
        path, _, point = target.rpartition(":")
        x, _, y = point.partition(",")
        wanted = tuple(int(value) for value in expected.split(","))
        pixel = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf",
                                f"crop=1:1:{int(x)}:{int(y)}", "-frames:v", "1",
                                "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                               capture_output=True).stdout
        if len(pixel) != 3:
            print(f"  FAIL  no pixel at {x},{y} of {path}")
            return 1
        ok = all(abs(a - b) <= args.tolerance for a, b in zip(pixel, wanted))
        print(f"  {'ok  ' if ok else 'FAIL'}  pixel {x},{y} of {path} is {list(pixel)}, "
              f"wanted {list(wanted)} +-{args.tolerance}")
        return 0 if ok else 1

    display = os.environ.get("DISPLAY", "")
    if not display:
        print("  skipped (no DISPLAY; a real window needs the session display)")
        return 0
    if args.selftest:
        method = args.capture
        if method == "auto":
            method = "desktop" if os.environ.get("WAYLAND_DISPLAY") else "x11"
        if method == "desktop" and not shutil.which("flameshot"):
            print("  skipped (desktop capture needs flameshot)")
            return 0
        for tool in ("ffmpeg", "xwininfo", "xprop"):
            if not shutil.which(tool):
                print(f"  skipped ({tool} missing)")
                return 0
        root = subprocess.run(["xwininfo", "-root"], capture_output=True, text=True).stdout
        screen = (int(re.search(r"Width:\s+(\d+)", root).group(1)),
                  int(re.search(r"Height:\s+(\d+)", root).group(1)))
        return selftest(args, method, display, screen)
    if args.game_dir is None or not args.game_dir.is_dir():
        print("  skipped (no game directory; pass --game-dir or set RAGE_GAME_DIR)")
        return 0
    if not args.exe.is_file():
        print("  skipped (no executable)")
        return 0
    for tool in ("ffmpeg", "xwininfo", "xprop"):
        if not shutil.which(tool):
            print(f"  skipped ({tool} missing)")
            return 0
    method = args.capture
    if method == "auto":
        # An X11 grab of a Wayland session reads a black framebuffer; the screen behind the
        # windows is only visible through the compositor's screenshot API.
        method = "desktop" if os.environ.get("WAYLAND_DISPLAY") else "x11"
    if method == "desktop" and not shutil.which("flameshot"):
        print("  skipped (desktop capture needs flameshot)")
        return 0
    from rage import proton_wine
    wine = proton_wine()
    if wine is None:
        print("  skipped (no Proton wine; set PROTON_WINE)")
        return 0

    root = subprocess.run(["xwininfo", "-root"], capture_output=True, text=True).stdout
    screen = (int(re.search(r"Width:\s+(\d+)", root).group(1)),
              int(re.search(r"Height:\s+(\d+)", root).group(1)))

    stubs = ROOT / "cache/stubs"
    build = subprocess.run([sys.executable, str(ROOT / "tools/stub_dlls.py"),
                            str(args.exe), "--out", str(stubs)],
                           capture_output=True, text=True)
    if build.returncode != 0:
        print(build.stdout[-300:], build.stderr[-300:])
        return 1
    from run_dir import stage
    # Staging keeps the package read-only; the stub DLLs are the only files written.
    game, links, placed = stage(args.game_dir, ROOT / "cache/run", stubs)
    print(f"  run directory {game} ({links} linked, {placed} stubs); the dump is not written")

    work = Path(tempfile.mkdtemp(prefix="bootframes-"))
    frames_dir = ROOT / "cache/frames" / time.strftime("%Y%m%dT%H%M%S")
    frames_dir.mkdir(parents=True, exist_ok=True)
    index = (frames_dir / "index.tsv").open("w")
    index.write("t\tframe\tcontrast\tlit\tmotion\tsplash_ssim\n")
    log_path = work / "run.log"
    exe = game / "bootframe.exe"
    exe.write_bytes(args.exe.read_bytes())
    env = dict(os.environ, WINEPREFIX=os.environ.get(
        "PROTON_PREFIX", str(Path.home() / ".proton-vi/pfx")), STUB_TRACE="1")

    launch = [str(wine)]
    if not args.online:
        if not shutil.which("unshare"):
            print("  skipped (unshare missing; pass --online to run with the network up)")
            return 0
        # The image's Breakpad reporter posts a minidump to the publisher's Backtrace
        # project for every fault it catches; a test run has no business doing that.
        launch = ["unshare", "-rn"] + launch
    print("  ACCEPTANCE: the console image (this is the one that must pass)")
    print(f"  capture {method} on {display}, screen {screen[0]}x{screen[1]}, "
          f"network {'up' if args.online else 'off'}")
    splash = args.splash
    if splash is None:
        splash = args.game_dir / "xbs_splash.png"
    splash = splash if splash.is_file() else None
    if splash is not None:
        print(f"  artwork reference {splash.name}")
    before = windows()
    process = None
    window = None
    rect = None
    frames = 0
    grabs = 0
    failures = 0
    first_failure = ""
    best = (0, 0.0, 0.0)
    best_splash = (0.0, None)
    still = 0
    settled_at = None
    clicked = False
    answered = False
    clicked_at = None
    minimized = 0
    previous = None
    last = None
    timeline = []
    try:
        with open(log_path, "w") as sink:
            process = subprocess.Popen(launch + [str(exe)], cwd=str(game),
                                       env=env, stdout=sink, stderr=subprocess.STDOUT)
        deadline = time.time() + args.seconds
        while time.time() < deadline:
            if process.poll() is not None:
                break
            if window is None:
                window = pick_window(before, descendants(process.pid),
                                     [exe.stem.lower(), *args.window_name])
                if window is None:
                    time.sleep(0.5)
                    continue
                rect = rectangle(window)
                if rect is None:
                    window = None
                    continue
                title = windows().get(window, ("",))[0] or "(untitled)"
                print(f"  window {window} \"{title}\" at {rect[2]}x{rect[3]}+{rect[0]}+{rect[1]}")
            grabs += 1
            started = time.time()
            frame, error = capture(method, screen, rect, display)
            if frame is None:
                failures += 1
                first_failure = first_failure or error
                time.sleep(1)
                continue
            contrast, deviation, lit = spread(frame)
            delta = motion(previous, frame)
            previous = frame
            last = (rect, frame)
            hidden = minimize_state(window) == "hidden"
            minimized += 1 if hidden else 0
            if (contrast, deviation, lit) > best:
                best = (contrast, deviation, lit)
            carries = not hidden and contrast >= args.min_spread and lit >= args.min_lit
            if carries:
                frames += 1
            still = still + 1 if (carries and delta <= args.max_motion) else 0
            if settled_at is None and still >= args.settle:
                settled_at = time.time()
            if settled_at and not clicked and args.click:
                x, y, width, height = rect
                subprocess.run(["xdotool", "mousemove", str(x + width // 2),
                                str(y + height // 2), "click", "1"], capture_output=True)
                clicked = True
                clicked_at = time.time()
            elif clicked and not answered and delta > args.max_motion:
                answered = True
            number = len(timeline)
            png = frames_dir / f"{number:04d}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo",
                            "-pix_fmt", "gray", "-s", f"{WIDTH}x{HEIGHT}", "-i", "pipe:0",
                            "-frames:v", "1", str(png)], input=frame, capture_output=True)
            splash_ssim = None
            if splash is not None:
                splash_ssim, _ = similarity(str(png), str(splash))
                if splash_ssim is not None and splash_ssim > best_splash[0]:
                    best_splash = (splash_ssim, png.name)
            index.write(f"{number}\t{png.name}\t{contrast}\t{lit:.4f}\t{delta:.2f}"
                        f"\t{'' if splash_ssim is None else f'{splash_ssim:.4f}'}\n")
            index.flush()
            timeline.append(f"    {len(timeline):3d}  contrast {contrast:3d}  lit {lit:5.1%}  "
                            f"motion {delta:6.2f}{'  still' if still else ''}"
                            f"{'  minimized' if hidden else ''}")
            time.sleep(max(0.0, 1.0 - (time.time() - started)))
    finally:
        alive = process is not None and process.poll() is None
        if process is not None and alive:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        exe.unlink(missing_ok=True)

    index.close()
    for line in timeline[-20:]:
        print(line)
    print(f"  frames kept in {frames_dir.relative_to(ROOT)}")
    log = log_path.read_text(errors="replace") if log_path.is_file() else ""
    exit_code = process.returncode if process is not None else None
    print(f"  exit {exit_code}, window {window or 'none'}, grabs {grabs} ({failures} failed), "
          f"content frames {frames}, best contrast {best[0]}, deviation {best[1]:.1f}, "
          f"lit {best[2]:.1%}, settled {'yes' if settled_at else 'no'}")

    check("the process starts", process is not None and exit_code is not None)
    check("the display can be captured", failures == 0,
          f"({failures}/{grabs} failed: {first_failure})" if failures else "")
    check("a window opens on the session display", window is not None)
    check(f"it draws at least {args.min_frames} frames with content",
          frames >= args.min_frames, f"({frames})")
    check("the screen carries content, not just a cursor", best[2] >= args.min_lit,
          f"({best[2]:.1%} lit)")
    check(f"the content settles for {args.settle} s after the videos",
          settled_at is not None, "(the menu)")
    if splash is not None:
        check(f"a frame matches the package's artwork ({splash.name}) beyond "
              f"SSIM {args.min_splash_ssim}",
              best_splash[0] >= args.min_splash_ssim,
              f"(best {best_splash[0]:.4f}"
              + (f" at {best_splash[1]}" if best_splash[1] else "") + ")")
    check("the menu answers a click", answered,
          "(the picture changed after the click)" if clicked else "(never clicked)")
    if minimized:
        print(f"  note  the window was minimized for {minimized} samples; those do not count")
    if last is not None:
        time.sleep(1)
        after, error = capture(method, screen, last[0], display)
        left = motion(last[1], after) if after else 0.0
        check("the scored rectangle belongs to the game", left > 0.5,
              f"(after exit the rectangle {'changed' if left > 0.5 else 'did not change'}, "
              f"motion {left:.2f}" + (f"; {error}" if error else "") + ")")
    if "submit.backtrace.io" in log or "HTTP Return code" in log:
        # Measured 2026-11-25: the image's Breakpad reporter posts a minidump to the
        # publisher's Backtrace project when it catches a fault. A test run should not do
        # that quietly, so it is reported and blocked before the next one.
        print("  note  the crash reporter posted a minidump to submit.backtrace.io; "
              "keep the network off for test runs")
    if not frames:
        for line in log.splitlines()[-6:]:
            print(f"    {line}")
    if log_path.is_file():
        shutil.copy(log_path, ROOT / "cache/boot-frames.log")

    if window is None:
        for known, (title, width, height, _x, _y) in windows().items():
            if known not in before:
                print(f"    unattributed window {known} \"{title}\" {width}x{height} "
                      f"classes {sorted(window_classes(known))}; pass --window-name to claim it")
    print()
    print("PASS" if not FAILED else f"FAIL: {len(FAILED)} check(s)")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
