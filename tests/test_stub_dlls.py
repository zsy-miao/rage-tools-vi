"""The stub generator: classification, exports, and a real import table.

The console image is the fixture when it is present; the classification rules are tested
without it. Building a stub needs mingw, so that check skips when the cross compiler is
absent.

    python3 tests/test_stub_dlls.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

FAILED = []


def check(name, condition, detail=""):
    print(f"  {'ok  ' if condition else 'FAIL'}  {name} {detail}")
    if not condition:
        FAILED.append(name)


def main():
    from stub_dlls import is_console, pe_imports, write_stub

    print("classification")
    for dll in ("xg_xs.dll", "d3d12_xs.dll", "xapu.dll", "xmem.dll", "AcpHal.dll",
                "XCRDAPI.dll", "XboxBvhBuilder.dll", "libHttpClient.GDK.dll"):
        check(f"{dll} is a console library", is_console(dll))
    for dll in ("kernel32.dll", "user32.dll", "d3d12.dll"):
        check(f"{dll} is not", not is_console(dll))

    exe = ROOT / "cache/exe/game_scarlett_master.exe"
    if exe.is_file():
        print("import table")
        imports = pe_imports(exe)
        check("library count", len(imports) == 68, f"({len(imports)})")
        names = {name.lower() for name in imports}
        check("console libraries present",
              {"xg_xs.dll", "d3d12_xs.dll", "xmem.dll", "xapu.dll"} <= names)
        check("system libraries present", {"advapi32.dll", "ws2_32.dll"} <= names)
        console = {dll: symbols for dll, symbols in imports.items() if is_console(dll)}
        check("console imports to stub", len(console) == 14, f"({len(console)})")
    else:
        print("import table: skipped (executable not present)")

    if shutil.which("x86_64-w64-mingw32-gcc"):
        print("stub build")
        with tempfile.TemporaryDirectory() as work:
            out = Path(work)
            ok = write_stub(out, "xg_xs.dll", [("name", "XGSuggestSwizzleMode"),
                                               ("name", "XGCreateTextureComputer"),
                                               ("ordinal", 7)])
            check("builds a DLL", ok and (out / "xg_xs.dll").is_file())
            exports = (out / "xg_xs_dll.def").read_text()
            check("every import is exported",
                  "XGSuggestSwizzleMode" in exports and "XGCreateTextureComputer" in exports)
            check("ordinals carry NONAME", "@7 NONAME" in exports)
            mangled = write_stub(out, "m.dll", [("name", "??0Thing@@QEAA@XZ")])
            check("a mangled name is aliased", mangled and "=stub_0" in (out / "m_dll.def").read_text())
    else:
        print("stub build: skipped (no mingw cross compiler)")

    print()
    print("PASS" if not FAILED else f"FAIL: {len(FAILED)} check(s)")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
