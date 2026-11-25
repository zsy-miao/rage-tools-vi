"""The pixel check itself, tested: exact pixels pass, wrong pixels fail, blanks are caught.

`tests/test_boot_frames.py --assert-pixel FILE:X,Y=R,G,B` is the check that decides whether a
kept frame shows what it should — the Rockstar logo, a menu, anything. A check that can only
say "ok" is worthless, so this builds frames with known pixels and requires both answers:

    python3 tests/test_boot_pixels.py

No display is needed: the frames are generated with ffmpeg from raw pixels.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAMES = ROOT / "tests/test_boot_frames.py"
FAILED = []


def check(name, condition, detail=""):
    print(f"  {'ok  ' if condition else 'FAIL'}  {name} {detail}")
    if not condition:
        FAILED.append(name)
    return condition


def frame(path, width, height, colour):
    """Write a solid-colour PNG."""
    raw = bytes(colour) * (width * height)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                    "-s", f"{width}x{height}", "-i", "pipe:0", "-frames:v", "1", str(path)],
                   input=raw, check=True)


def split_frame(path, width, height):
    """Half white, half black: a frame with more than one colour in it."""
    row = bytes((255, 255, 255)) * (width // 2) + bytes((0, 0, 0)) * (width // 2)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                    "-s", f"{width}x{height}", "-i", "pipe:0", "-frames:v", "1", str(path)],
                   input=row * height, check=True)


def assert_pixel(path, x, y, rgb, tolerance=10):
    """Run the check the scoreboard uses and return (ok, output)."""
    expectation = f"{path}:{x},{y}={rgb[0]},{rgb[1]},{rgb[2]}"
    result = subprocess.run([sys.executable, str(FRAMES), "--assert-pixel", expectation,
                             "--tolerance", str(tolerance)],
                            capture_output=True, text=True)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def assert_compare(frame, reference, min_ssim):
    result = subprocess.run([sys.executable, str(FRAMES), "--compare-frame",
                             f"{frame}:{reference}", "--min-ssim", str(min_ssim)],
                            capture_output=True, text=True)
    return result.returncode == 0, (result.stdout + result.stderr).strip()


def main():
    work = Path(tempfile.mkdtemp(prefix="pixels-"))
    white = work / "white.png"
    dark = work / "dark.png"
    frame(white, 64, 48, (255, 255, 255))
    frame(dark, 64, 48, (0, 0, 0))
    rendered = work / "rendered.png"
    split_frame(rendered, 64, 48)

    ok, output = assert_pixel(white, 10, 10, (255, 255, 255))
    check("a matching pixel passes", ok, output.splitlines()[-1] if output else "")
    ok, output = assert_pixel(white, 10, 10, (0, 0, 0))
    check("a wrong expectation fails", not ok, output.splitlines()[-1] if output else "")
    ok, _ = assert_pixel(white, 32, 24, (255, 255, 250))
    check("a difference inside the tolerance passes", ok)
    ok, _ = assert_pixel(dark, 0, 0, (40, 40, 40))
    check("a difference outside the tolerance fails", not ok)
    ok, output = assert_pixel(work / "absent.png", 0, 0, (0, 0, 0))
    check("a missing frame fails rather than passing quietly", not ok, output.splitlines()[-1])

    # SSIM/PSNR against a reference: identical passes, a changed frame fails.
    ok, output = assert_compare(white, white, 0.99)
    check("an identical frame passes SSIM 1.0", ok, output.splitlines()[-1] if output else "")
    ok, output = assert_compare(white, dark, 0.99)
    check("a different frame fails SSIM", not ok, output.splitlines()[-1] if output else "")

    # A whole-frame census: a blank frame has one colour, a rendered one has many.
    for name, path, expect_distinct in (("blank frame", dark, 1), ("rendered frame", rendered, 2)):
        data = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo",
                               "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        distinct = len({data[i:i + 3] for i in range(0, len(data), 3)})
        check(f"{name} has {expect_distinct} distinct colour(s)", distinct == expect_distinct,
              f"({distinct})")

    print()
    print("PASS" if not FAILED else f"FAIL: {len(FAILED)} check(s)")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
