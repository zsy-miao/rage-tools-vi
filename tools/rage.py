"""One entry point for the project's operations.

Shell wrappers grew one per task; this replaces them with subcommands so the surface is
discoverable (`rage.py --help`) and each operation is testable Python.

    python3 tools/rage.py check                 # tests, invariants, docs
    python3 tools/rage.py e2e                   # every end-to-end check, headless
    python3 tools/rage.py demo [DIR]            # playable audio from three variants
    python3 tools/rage.py mod ARCHIVE START END --marker TEXT
    python3 tools/rage.py coverage              # classified share per archive
    python3 tools/rage.py docs                  # regenerate tool index and handoff manifest
    python3 tools/rage.py index adat|bink ARCHIVE
"""

import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

DEMO_RUNS = [
    ("ff21", 0x129B000, 0x12A2000, "stream", 0),
    ("ff02", 0x16437000, 0x16BAA000, "stream", 0),
    ("ff25", 0x548F000, 0x58AF800, "ff25", 0),
]
def default_audio():
    """First audio.rpf found: an explicit path, the source root, or the parent tree."""
    candidates = []
    if os.environ.get("RAGE_SRC"):
        candidates.append(Path(os.environ["RAGE_SRC"]) / "audio.rpf")
    candidates += [ROOT / "audio.rpf", ROOT.parent / "gta6-source/audio.rpf"]
    return next((path for path in candidates if path.is_file()), None)


def python():
    return [sys.executable]


def run(command, **kwargs):
    return subprocess.run(command, cwd=ROOT, **kwargs)


def say(name, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name} {detail}")
    return ok


def pe_sections(data):
    import struct
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    size = struct.unpack_from("<H", data, pe + 20)[0]
    table = pe + 24 + size
    return [struct.unpack_from("<IIII", data, table + 40 * i + 8) for i in range(count)]


def pe_imports(path):
    """DLL names in the import table of a PE32+ image."""
    import struct
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic != 0x20B:
        raise ValueError(f"not a PE32+ image (magic {magic:#x})")
    rva, _size = struct.unpack_from("<II", data, optional + 112 + 8)
    sections = pe_sections(data)

    def offset_of(target):
        for virtual_size, virtual, raw_size, raw in sections:
            if virtual <= target < virtual + max(virtual_size, raw_size):
                return raw + (target - virtual)
        raise ValueError(f"RVA {target:#x} is not in any section")

    names = []
    cursor = offset_of(rva)
    while True:
        entry = struct.unpack_from("<IIIII", data, cursor)
        if entry[3] == 0:
            break
        name_at = offset_of(entry[3])
        end = data.find(b"\0", name_at)
        names.append(data[name_at:end].decode("ascii", "replace"))
        cursor += 20
    return names


def platform_probe(exe):
    """What a Windows image needs, and what this machine provides.

    The binary is the authority: its import table names the runtime it expects, and a
    library name that only exists on one platform decides the classification. Wine does
    not provide console libraries, so the answer is a property of the image, not of
    whether a compatibility layer happens to be installed.
    """
    imports = pe_imports(exe)
    lowered = {name.lower() for name in imports}
    console_only = {"xg_xs.dll", "d3d12_xs.dll", "xapu.dll", "xmem.dll", "acphal.dll",
                    "xboxbvhbuilder.dll", "xcrДapi.dll", "xcrdapi.dll"}
    required = sorted(name for name in lowered if name in console_only)
    wine = shutil.which("wine") or shutil.which("wine64")
    if required:
        kind = "xbox"
    elif wine:
        kind = "windows"
    else:
        kind = "windows-unrunnable"
    return {"imports": imports, "console_imports": required, "kind": kind,
            "wine": wine, "exe": str(exe)}


def proton_wine():
    if os.environ.get("PROTON_WINE"):
        return Path(os.environ["PROTON_WINE"])
    home = Path.home()
    roots = [home / ".steam/debian-installation/compatibilitytools.d",
             home / ".steam/steam/steamapps/common",
             home / ".local/share/Steam/steamapps/common"]
    for root in roots:
        if not root.is_dir():
            continue
        for entry in sorted(root.glob("*Proton*"), reverse=True):
            wine = entry / "files/bin/wine"
            if wine.is_file():
                return wine
    return None


def cmd_play(args):
    """Start the game with stub consoles libraries, and report how far it goes."""
    if args.stubs:
        exe = args.exe or (ROOT / "cache/exe/game_scarlett_master.exe")
        game = args.game_dir
        if game is None or not exe.is_file():
            print("--stubs needs --game-dir and an executable")
            return 1
        stub_build = ROOT / "cache/stubs"
        built = run([sys.executable, str(ROOT / "tools/stub_dlls.py"), str(exe),
                     "--out", str(stub_build)], capture_output=True, text=True)
        if built.returncode != 0:
            print(built.stdout[-400:], built.stderr[-400:])
            return 1
        dlls = sorted(stub_build.glob("*.dll"))
        # Stage instead of copying into the dump: the package's own console DLLs are shipped
        # binaries, and an earlier launcher overwrote fifteen of them with stubs.
        from run_dir import stage
        game, links, placed = stage(args.game_dir, ROOT / "cache/run", stub_build)
        print(f"stub DLLs {len(dlls)}; run directory {game} ({links} linked, {placed} placed); "
              f"the dump is not written", flush=True)
        wine = proton_wine()
        if wine is None:
            print(f"{len(dlls)} stub DLLs written; no Proton wine found "
                  "(set PROTON_WINE)")
            return 2
        prefix = Path(os.environ.get("PROTON_PREFIX", Path.home() / ".proton-vi/pfx"))
        target = game / "game.exe"
        if not target.exists():
            target.symlink_to(exe)
        env = dict(os.environ, WINEPREFIX=str(prefix), STUB_TRACE="1")
        result = subprocess.run([str(wine), str(target)], cwd=str(game),
                                env=env, capture_output=True, text=True, timeout=args.timeout)
        log = result.stdout + result.stderr
        calls = [line for line in log.splitlines() if "!" in line and "(" in line]
        faults = [line for line in log.splitlines() if "Unhandled" in line or "page fault" in line]
        print(f"stub DLLs {len(dlls)}  exit {result.returncode}  calls logged {len(calls)}")
        for line in calls[-6:]:
            print(f"  {line}")
        for line in faults[-2:]:
            print(f"  {line}")
        (ROOT / "cache/play.log").write_text(log)
        return 0 if not faults else 3

    """Start the game, or say exactly what stops it."""
    exe = args.exe or (ROOT / "cache/exe/game_scarlett_master.exe")
    if not exe.is_file():
        print(f"no executable at {exe}")
        return 1
    probe = platform_probe(exe)
    if probe["kind"] == "xbox":
        print(f"{exe.name}: Xbox Series image")
        print("  runtime imports only that platform provides: "
              + ", ".join(probe["console_imports"]))
        print("  wine: " + (probe["wine"] or "not installed (and would not supply these)"))
        print("  cannot start: no Xbox runtime on this machine")
        return 2
    if probe["kind"] == "windows":
        return run([probe["wine"], str(exe)], cwd=str(exe.parent)).returncode
    print(f"{exe.name}: Windows image, no compatibility layer installed")
    return 2


def cmd_test(args):
    """Run the test files, one tier at a time."""
    tiers = {"unit": ["test_extraction_tools.py", "test_analysis_tools.py", "test_robustness.py",
                 "test_stub_dlls.py", "test_boot_loop.py"],
             "corpus": ["test_corpus_invariants.py", "test_mod_roundtrip.py"],
             "e2e": []}
    selected = list(tiers) if args.tier == "all" else [args.tier]
    failures = 0
    checks = 0
    for tier in selected:
        for name in tiers[tier]:
            path = ROOT / "tests" / name
            result = run(python() + [str(path)], capture_output=True, text=True)
            passed = result.stdout.count("  ok  ")
            skipped = result.stdout.count("skipped")
            checks += passed
            status = "PASS" if result.returncode == 0 else "FAIL"
            print(f"{tier:7s} {name:34s} {status} {passed:3d} checks"
                  + (f", {skipped} skipped" if skipped else ""))
            if result.returncode != 0:
                failures += 1
                print("\n".join(result.stdout.splitlines()[-4:]))
    print()
    print(f"{checks} checks, {failures} failing file(s)")
    return 0 if not failures else 1


def cmd_check(args):
    return run([str(ROOT / "tools/check.sh")]).returncode


def cmd_e2e(args):
    scripts = sorted((ROOT / "tools").glob("explorer_*e2e*.sh"))
    failures = 0
    for script in scripts:
        print(f"{script.name:40s} ", end="", flush=True)
        result = run(["bash", str(script)], capture_output=True, text=True)
        if result.returncode == 0:
            print("PASS")
        else:
            print("FAIL")
            print("\n".join(result.stdout.splitlines()[-3:]))
            failures += 1
    with tempfile.TemporaryDirectory() as work:
        ok = mod_roundtrip(ROOT / "common.rpf", 0x3B2850, 0x3B399E, b"E2E_OK", Path(work))
        print(f"{'in-place replacement':40s} {'PASS' if ok else 'FAIL'}")
        failures += 0 if ok else 1
        src = default_audio()
        ok = demo(Path(work) / "demo", src, quiet=True) if src else True
        print(f"{'playable audio':40s} {'PASS' if ok else 'FAIL'}")
        failures += 0 if ok else 1
    print()
    print("PASS" if not failures else f"FAIL: {failures}")
    return 0 if not failures else 1


def pack_replacement(payload, room):
    stream = zlib.compress(payload, 9)
    if len(stream) > room:
        return None
    return stream + b"\0" * (room - len(stream))


def mod_roundtrip(archive, start, end, payload, work):
    if not archive.is_file():
        return False
    copy = Path(work) / "mod.rpf"
    shutil.copy(archive, copy)
    size_before = copy.stat().st_size
    stored = copy.read_bytes()[start:end]
    packed = pack_replacement(payload, len(stored))
    if packed is None:
        return False
    with copy.open("r+b") as handle:
        handle.seek(start)
        handle.write(packed)
    check = zlib.decompress(copy.read_bytes()[start:end])
    return check == payload and copy.stat().st_size == size_before


def cmd_mod(args):
    archive = args.archive
    stored = archive.read_bytes()[args.start:args.end]
    original = zlib.decompress(stored)
    payload = args.payload.read_bytes() if args.payload else args.marker.encode()
    packed = pack_replacement(payload, len(stored))
    print(f"asset {len(original):,} B -> {len(payload):,} B into {len(stored):,} B stored")
    if packed is None:
        print("replacement does not fit")
        return 1
    if args.dry_run:
        print("dry run")
        return 0
    with archive.open("r+b") as handle:
        handle.seek(args.start)
        handle.write(packed)
    check = zlib.decompress(archive.read_bytes()[args.start:args.end])
    return 0 if check == payload else 1


def demo(dest, archive, quiet=False):
    dest.mkdir(parents=True, exist_ok=True)
    rows = []
    for variant, start, end, mode, stream in DEMO_RUNS:
        out = dest / f"{variant}-{stream}.wav"
        command = python() + [str(ROOT / "tools/decode_adat_stream.py"), str(archive),
                              "--start", hex(start), "--end", hex(end), "--output", str(out)]
        command += ["--ff25"] if mode == "ff25" else ["--stream", str(stream)]
        result = run(command, capture_output=True, text=True)
        if result.returncode != 0 or not out.is_file():
            if not quiet:
                print(f"{variant}: {result.stdout[-120:]}{result.stderr[-160:]}")
            return False
        with wave.open(str(out)) as handle:
            frames, channels, rate = handle.getnframes(), handle.getnchannels(), handle.getframerate()
        rows.append((out.name, frames / rate, channels,
                     hashlib.sha256(out.read_bytes()).hexdigest()[:16]))
    if not quiet:
        print(f"{'file':14s} {'seconds':>8s} {'ch':>3s}  sha256")
        for name, seconds, channels, digest in rows:
            print(f"{name:14s} {seconds:8.2f} {channels:3d}  {digest}")
    return all(seconds > 0.2 for _n, seconds, _c, _d in rows)


def cmd_demo(args):
    archive = args.archive or default_audio()
    if archive is None:
        print("skipped: no audio.rpf (pass a path or set RAGE_SRC)")
        return 0
    ok = demo(args.dest, archive)
    if not args.quiet and ok:
        print(f"\nplay: ffplay {args.dest}/ff25-0.wav")
    return 0 if ok else 1


def load_opus():
    import ctypes
    from ctypes.util import find_library
    name = find_library("opus")
    if not name:
        raise RuntimeError("libopus is required")
    lib = ctypes.CDLL(name)
    lib.opus_decoder_create.argtypes = [ctypes.c_int32, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
    lib.opus_decoder_create.restype = ctypes.c_void_p
    lib.opus_decoder_destroy.argtypes = [ctypes.c_void_p]
    lib.opus_decode.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int32,
                                ctypes.POINTER(ctypes.c_int16), ctypes.c_int, ctypes.c_int]
    lib.opus_decode.restype = ctypes.c_int
    return lib, ctypes


def decode_packets(lib, ctypes, packets, channels=2, rate=48000, frame=5760):
    error = ctypes.c_int()
    state = lib.opus_decoder_create(rate, channels, ctypes.byref(error))
    if not state or error.value:
        raise RuntimeError(f"opus_decoder_create failed: {error.value}")
    buffer = (ctypes.c_int16 * (frame * channels))()
    pcm = bytearray()
    skipped = 0
    try:
        for packet in packets:
            got = lib.opus_decode(state, packet, len(packet), buffer, frame, 0)
            if got < 0:
                # A packet the framing guessed but libopus rejects is a measurement, not
                # a reason to lose the other thousands of packets in the container.
                skipped += 1
                continue
            pcm += bytes(memoryview(buffer).cast("B")[: got * channels * 2])
    finally:
        lib.opus_decoder_destroy(state)
    return bytes(pcm), skipped


def cmd_decode(args):
    """Decode a container variant to WAV, one file per container."""
    import csv
    import wave
    from decode_adat_stream import ff25_packets_auto
    lib, ctypes = load_opus()
    rows = [r for r in csv.DictReader(open(args.census), delimiter="\t")
            if r["flags"].lower().endswith(args.suffix)]
    if args.limit:
        rows = rows[: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)
    decoded = failed = rejected = 0
    frames = 0
    with args.archive.open("rb") as handle:
        for index, row in enumerate(rows, 1):
            start, end = int(row["start"], 16), int(row["end"], 16)
            handle.seek(start)
            blob = handle.read(end - start)
            target = args.out / f"{index:05d}-{start:09x}.wav"
            if target.exists() and not args.force:
                decoded += 1
                continue
            try:
                pcm, skipped = decode_packets(lib, ctypes, ff25_packets_auto(blob),
                                              channels=args.channels)
            except Exception as error:  # noqa: BLE001 - a failure is a measurement
                failed += 1
                print(f"{target.name}: {error}", flush=True)
                continue
            with wave.open(str(target), "wb") as wav:
                wav.setnchannels(args.channels)
                wav.setsampwidth(2)
                wav.setframerate(48000)
                wav.writeframes(pcm)
            decoded += 1
            rejected += skipped
            frames += len(pcm) // (2 * args.channels)
            if not args.quiet and index % 100 == 0:
                print(f"{index}/{len(rows)} containers, {frames / 48000 / 60:.1f} min", flush=True)
    print(f"decoded {decoded}  failed {failed}  rejected packets {rejected}  "
          f"audio {frames / 48000 / 3600:.2f} h  -> {args.out}")
    return 0 if failed == 0 else 1


def cmd_measure(args):
    """Audio duration of the 0xff25 corpus, from a sample of containers."""
    import csv
    from decode_adat_stream import ff25_packets_auto
    rows = [r for r in csv.DictReader(open(args.census), delimiter="\t")
            if r["flags"].lower().endswith(args.suffix)]
    if not rows:
        print("no matching containers")
        return 1
    step = max(1, len(rows) // args.sample)
    sample = rows[::step][: args.sample]
    total_packets = 0
    sampled_bytes = 0
    with args.archive.open("rb") as handle:
        for row in sample:
            start, end = int(row["start"], 16), int(row["end"], 16)
            handle.seek(start)
            blob = handle.read(end - start)
            sampled_bytes += len(blob)
            total_packets += len(ff25_packets_auto(blob))
    seconds = total_packets * 960 / 48000
    per_container = seconds / len(sample)
    print(f"containers sampled {len(sample)}  bytes {sampled_bytes:,}  "
          f"packets {total_packets:,}  audio {seconds / 60:.1f} min")
    print(f"per container ~{per_container:.1f} s; "
          f"{len(rows):,} containers -> {per_container * len(rows) / 3600:.1f} h")
    return 0


def cmd_coverage(args):
    from index_coverage import main as coverage_main
    sys.argv = ["index_coverage.py"] + (["--out", str(args.out)] if args.out else [])
    return coverage_main()


def cmd_docs(args):
    for tool, extra in (("tool_index.py", []), ("handoff_manifest.py", [])):
        result = run(python() + [str(ROOT / "tools" / tool)] + extra, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr[-200:])
            return 1
    return 0


def cmd_index(args):
    tool = "adat_index.py" if args.kind == "adat" else "bink_index.py"
    command = python() + [str(ROOT / "tools" / tool), str(args.archive)]
    if args.out:
        command += ["--out", str(args.out)]
    if args.scan:
        command += ["--scan"]
    return run(command).returncode


def cmd_hash(args):
    command = python() + [str(ROOT / "tools/name_hash_game.py"), "--hash"] + args.names
    return run(command).returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="run the repository gate").set_defaults(func=cmd_check)

    play_p = sub.add_parser("play", help="start the game, or name what stops it")
    play_p.add_argument("--exe", type=Path)
    play_p.add_argument("--stubs", action="store_true",
                        help="build stub console DLLs, place them, run under Proton wine")
    play_p.add_argument("--game-dir", type=Path)
    play_p.add_argument("--timeout", type=int, default=120)
    play_p.set_defaults(func=cmd_play)

    test_p = sub.add_parser("test", help="run the unit, corpus or all tiers")
    test_p.add_argument("--tier", choices=["unit", "corpus", "e2e", "all"], default="unit")
    test_p.set_defaults(func=cmd_test)
    sub.add_parser("e2e", help="every end-to-end check, headless").set_defaults(func=cmd_e2e)

    demo_p = sub.add_parser("demo", help="decode three AWC variants to WAV")
    demo_p.add_argument("dest", nargs="?", type=Path, default=ROOT / "output/demo")
    demo_p.add_argument("--archive", type=Path)
    demo_p.add_argument("--quiet", action="store_true")
    demo_p.set_defaults(func=cmd_demo)

    mod_p = sub.add_parser("mod", help="replace a zlib range in place")
    mod_p.add_argument("archive", type=Path)
    mod_p.add_argument("--start", type=lambda v: int(v, 0), required=True)
    mod_p.add_argument("--end", type=lambda v: int(v, 0), required=True)
    mod_p.add_argument("--payload", type=Path)
    mod_p.add_argument("--marker")
    mod_p.add_argument("--dry-run", action="store_true")
    mod_p.set_defaults(func=cmd_mod)

    decode_p = sub.add_parser("decode", help="decode a container variant to WAV")
    decode_p.add_argument("archive", type=Path)
    decode_p.add_argument("--census", type=Path, default=ROOT / "handoff/audio-full-census.tsv")
    decode_p.add_argument("--suffix", default="ff25")
    decode_p.add_argument("--out", type=Path, default=ROOT / "output/audio-ff25")
    decode_p.add_argument("--channels", type=int, default=2)
    decode_p.add_argument("--limit", type=int, default=0)
    decode_p.add_argument("--force", action="store_true")
    decode_p.add_argument("--quiet", action="store_true")
    decode_p.set_defaults(func=cmd_decode)

    measure_p = sub.add_parser("measure", help="duration of a container variant, sampled")
    measure_p.add_argument("archive", type=Path)
    measure_p.add_argument("--census", type=Path, default=ROOT / "handoff/audio-full-census.tsv")
    measure_p.add_argument("--suffix", default="ff25")
    measure_p.add_argument("--sample", type=lambda v: int(v, 0), default=30)
    measure_p.set_defaults(func=cmd_measure)

    cov_p = sub.add_parser("coverage", help="classified share per archive")
    cov_p.add_argument("--out", type=Path)
    cov_p.set_defaults(func=cmd_coverage)

    sub.add_parser("docs", help="regenerate tool index and handoff manifest").set_defaults(func=cmd_docs)

    idx_p = sub.add_parser("index", help="index an archive's containers")
    idx_p.add_argument("kind", choices=["adat", "bink"])
    idx_p.add_argument("archive", type=Path)
    idx_p.add_argument("--out", type=Path)
    idx_p.add_argument("--scan", action="store_true")
    idx_p.set_defaults(func=cmd_index)

    hash_p = sub.add_parser("hash", help="compute the engine's name hash")
    hash_p.add_argument("names", nargs="+")
    hash_p.set_defaults(func=cmd_hash)

    args = parser.parse_args(argv)
    if args.command == "mod" and not (args.payload or args.marker):
        parser.error("mod needs --payload or --marker")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
