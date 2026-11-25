"""Console-only imports of a Windows image, and stub DLLs that satisfy them.

The game is a console PE: Wine loads it and stops on libraries that only exist on that
platform (`xg_xs`, `d3d12_xs`, `xapu`, `xmem`, `AcpHal`, `XCRDAPI`, ...). This reads the
import table, writes a `.def` and a C stub for every symbol, and compiles the stubs with
mingw so the loader resolves them and execution can move past the import check.

A stub returns 0 and records its first call: the sequence of calls is the measurement of
how far the image gets.

    python3 tools/stub_dlls.py cache/exe/game_scarlett_master.exe --out cache/stubs
    python3 tools/stub_dlls.py <exe> --out <dir> --list
"""

import argparse
import re
import struct
import subprocess
import sys
from pathlib import Path

CONSOLE = {"xg_xs.dll", "d3d12_xs.dll", "xapu.dll", "xmem.dll", "acphal.dll",
           "xcrdapi.dll", "xboxbvhbuilder.dll", "chad.dll", "bink2scarlett.dll",
           "gameinput.dll", "libhttpclient.gdk.dll",
           "amd_fidelityfx_loader_xbox.dll", "amd_fidelityfx_upscaler_xbox.dll",
           "mfplat.dll", "mfreadwrite.dll", "xcurldll"}

MINGW = "x86_64-w64-mingw32-gcc"


def pe_imports(path):
    """{dll name: [symbol or ordinal, ...]} from a PE32+ import table."""
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    size = struct.unpack_from("<H", data, pe + 20)[0]
    table = pe + 24 + size
    sections = [struct.unpack_from("<IIII", data, table + 40 * i + 8) for i in range(count)]
    optional = pe + 24
    if struct.unpack_from("<H", data, optional)[0] != 0x20B:
        raise ValueError("not a PE32+ image")

    def offset_of(rva):
        for virtual_size, virtual, raw_size, raw in sections:
            if virtual <= rva < virtual + max(virtual_size, raw_size):
                return raw + (rva - virtual)
        raise ValueError(f"RVA {rva:#x} outside every section")

    def read_name(rva):
        at = offset_of(rva)
        return data[at:data.find(b"\0", at)].decode("ascii", "replace")

    imports = {}
    cursor = offset_of(struct.unpack_from("<I", data, optional + 112 + 8)[0])
    while True:
        original, _stamp, _chain, name_rva, first = struct.unpack_from("<IIIII", data, cursor)
        if not name_rva:
            break
        dll = read_name(name_rva).lower()
        symbols = []
        at = offset_of(original or first)
        while True:
            entry = struct.unpack_from("<Q", data, at)[0]
            if entry == 0:
                break
            if entry >> 63:
                symbols.append(("ordinal", entry & 0xFFFF))
            else:
                symbols.append(("name", read_name(entry + 2)))
            at += 8
        imports[dll] = symbols
        cursor += 20
    return imports


def is_console(dll):
    return dll.lower() in CONSOLE or dll.lower().endswith("_xs.dll") \
        or dll.lower().endswith("_xbox.dll") or "gdk" in dll.lower()


def write_stub(out, dll, symbols):
    stem = dll.rsplit(".", 1)[0].replace("-", "_")
    safe = dll.replace(".", "_").replace("-", "_")
    exports = []
    body = [f"/* stub for {dll}: {len(symbols)} imports */",
            "#include <stdio.h>",
            "#include <windows.h>",
            f'#define TRACE(name,a,b,c,d) do {{ if (getenv("STUB_TRACE")) {{ fprintf(stderr, "{dll}!%s(%llx,%llx,%llx,%llx)\\n", name,(unsigned long long)(a),(unsigned long long)(b),(unsigned long long)(c),(unsigned long long)(d)); }} }} while (0)',
            ""]
    for index, (kind, value) in enumerate(symbols):
        if kind == "name":
            name = value
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                body.append(f"unsigned long long {name}(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d) {{ TRACE(\"{name}\",a,b,c,d); return 0; }}")
                exports.append(f"  {name}")
            else:
                internal = f"stub_{index}"
                body.append(f"unsigned long long {internal}(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d) {{ TRACE(\"{name}\",a,b,c,d); return 0; }}")
                exports.append(f"  {name}={internal}")
        else:
            name = f"ord_{value}"
            body.append(f"unsigned long long {name}(unsigned long long a, unsigned long long b, unsigned long long c, unsigned long long d) {{ TRACE(\"{name}\",a,b,c,d); return 0; }}")
            exports.append(f"  {name} @{value} NONAME")
    (out / f"{safe}.def").write_text("EXPORTS\n" + "\n".join(exports) + "\n")
    custom = Path(__file__).resolve().parent / "stub_custom" / f"{dll}.c"
    if custom.is_file():
        (out / f"{safe}.c").write_text(custom.read_text())
    else:
        (out / f"{safe}.c").write_text("\n".join(body) + "\n")
    result = subprocess.run([MINGW, "-shared", "-Os", "-o", str(out / dll),
                             str(out / f"{safe}.c"), str(out / f"{safe}.def")],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  {dll}: {result.stderr.strip()[:300]}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("exe", type=Path)
    parser.add_argument("--out", type=Path, default=Path("cache/stubs"))
    parser.add_argument("--list", action="store_true", help="only print what is missing")
    parser.add_argument("--all", action="store_true",
                        help="stub every import, not only the console ones")
    args = parser.parse_args()

    imports = pe_imports(args.exe)
    wanted = {dll: symbols for dll, symbols in imports.items()
              if args.all or is_console(dll)}
    total = sum(len(symbols) for symbols in wanted.values())
    print(f"{len(imports)} libraries, {sum(len(v) for v in imports.values())} imports")
    print(f"{len(wanted)} console libraries, {total} imports to stub")
    for dll, symbols in sorted(wanted.items()):
        print(f"  {dll:34s} {len(symbols):5d} symbols")
    if args.list:
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    built = 0
    generated_ok = 0
    for dll, symbols in sorted(wanted.items()):
        ok = write_stub(args.out, dll, symbols)
        built += 1 if ok else 0
        generated_ok += 1 if ok else 0
    # Modules the image loads by name at runtime never appear in the import table.
    for source in sorted((Path(__file__).resolve().parent / "stub_custom").glob("*.dll.c")):
        dll = source.name[:-2]
        if dll in wanted:
            continue
        result = subprocess.run([MINGW, "-shared", "-Os", "-o", str(args.out / dll), str(source)],
                                capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  {dll}: {result.stderr.strip()[:300]}")
            continue
        built += 1
        print(f"  {dll:34s} {source.stat().st_size:5d} B source (runtime module)")
    print(f"built {built} stub DLLs in {args.out} "
          f"({generated_ok}/{len(wanted)} from imports)")
    return 0 if generated_ok == len(wanted) else 1


if __name__ == "__main__":
    sys.exit(main())
