"""Test an image for a commercial packer/protector instead of assuming one.

"For a protected binary you cannot read that code" is a claim like any other, and it is
either measurable or it is folklore. This measures it:

  * section layout and per-section entropy (packed code is near 8 bits per byte),
  * the standard protector section names and signature strings,
  * the share of `int3` bytes that are alignment padding versus debug-break guards (the
    two look identical in a hex dump and mean opposite things),
  * anti-debug and VM-detect idioms: `rdtsc`, `cpuid`, `sgdt`/`sidt`, `syscall`,
    `in`/`out`, `cli`/`sti`,
  * imports that protectors use (`IsDebuggerPresent`, `NtQueryInformationProcess`,
    `VirtualProtect`, thread enumeration) and whether a TLS callback exists.

A verdict is printed only when the numbers support one; otherwise the counts stand alone.

    python3 tools/protection_audit.py cache/exe/game_scarlett_master.exe
    python3 tools/protection_audit.py <exe> --json
"""

import argparse
import json
import math
import struct
import sys
from pathlib import Path

PROTECTOR_NAMES = (b".vmp0", b".vmp1", b".vmp2", b"themida", b"winlice", b".enigma",
                   b"UPX0", b"UPX1", b"petite", b".aspack", b".mpress", b".nsp",
                   b"pec1", b"pec2", b".ccg", b"enigma1", b"enigma2")

PROTECTOR_STRINGS = ("VMProtect", "Themida", "WinLicense", "Oreans", "Denuvo", "Enigma",
                     "ASProtect", "UPX!", "MPRESS", "SteamStub", "SecuROM", "StarForce",
                     "Armadillo", "Obsidium", "Code Virtualizer", "Custom Protection")

ANTI_DEBUG_IMPORTS = ("IsDebuggerPresent", "CheckRemoteDebuggerPresent",
                      "NtQueryInformationProcess", "NtSetInformationThread",
                      "NtQuerySystemInformation", "NtQueryObject",
                      "CreateToolhelp32Snapshot", "Process32First", "Process32Next",
                      "OutputDebugStringA", "OutputDebugStringW",
                      "VirtualProtect", "VirtualProtectEx", "NtProtectVirtualMemory",
                      "SetUnhandledExceptionFilter", "AddVectoredExceptionHandler",
                      "NtCreateThreadEx", "RtlAddVectoredExceptionHandler")

JCC_SHORT = range(0x70, 0x80)


def sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    table = pe + 24 + optional_size
    out = []
    for index in range(count):
        virtual_size, virtual, raw_size, raw = struct.unpack_from(
            "<IIII", data, table + 40 * index + 8)
        flags = struct.unpack_from("<I", data, table + 40 * index + 36)[0]
        name = data[table + 40 * index:table + 40 * index + 8].rstrip(b"\0")
        out.append({"name": name.decode("ascii", "replace"), "raw_name": name,
                    "virtual": virtual, "virtual_size": virtual_size,
                    "raw": raw, "raw_size": raw_size, "exec": bool(flags & 0x20000000)})
    return pe, out


def entropy(blob):
    if not blob:
        return 0.0
    counts = [0] * 256
    for byte in blob:
        counts[byte] += 1
    total = len(blob)
    return -sum((count / total) * math.log2(count / total) for count in counts if count)


def optional_header(data, pe):
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    image_base = struct.unpack_from("<Q", data, optional + 24)[0] if magic == 0x20B \
        else struct.unpack_from("<I", data, optional + 28)[0]
    entry = struct.unpack_from("<I", data, optional + 16)[0]
    count = struct.unpack_from("<I", data, optional + (108 if magic == 0x20B else 92))[0]
    directories = optional + (112 if magic == 0x20B else 96)
    return magic, image_base, entry, count, directories


def data_directory(data, directories, index):
    rva, size = struct.unpack_from("<II", data, directories + index * 8)
    return rva, size


def rva_offset(section_list, rva):
    for section in section_list:
        if section["virtual"] <= rva < section["virtual"] + section["raw_size"]:
            return section["raw"] + (rva - section["virtual"])
    return None


def classify_int3(text, start):
    """'padding' for a run of int3, 'guard' when a conditional jump jumps over it."""
    index = start
    while index < len(text) and text[index] == 0xCC:
        index += 1
    if index - start >= 2:
        return "padding"
    for back in range(1, 7):
        if start - back < 0:
            break
        previous = text[start - back]
        if previous in JCC_SHORT and text[start - back + 1] == 0x01:
            return "guard"
        if 0x80 <= previous <= 0x8F and start - back >= 1 and text[start - back - 1] == 0x0F:
            return "guard"
    return "other"


def scan(text):
    """Counts of the idioms that separate a debug build from a packed one."""
    counts = {"int3": 0, "guard": 0, "padding": 0, "other": 0,
              "rdtsc": 0, "cpuid": 0, "sgdt_sidt": 0, "syscall": 0}
    index = 0
    length = len(text)
    while index < length:
        byte = text[index]
        if byte == 0xCC:
            counts["int3"] += 1
            kind = classify_int3(text, index)
            counts[kind] += 1
            index += 1
            continue
        if byte == 0x0F and index + 1 < length:
            second = text[index + 1]
            if second == 0x31:
                counts["rdtsc"] += 1
                index += 2
                continue
            if second == 0xA2:
                counts["cpuid"] += 1
                index += 2
                continue
            if second == 0x05 and index > 0 and text[index - 1] == 0x0F:
                counts["syscall"] += 1
                index += 2
                continue
            if second == 0x01 and index + 2 < length:
                modrm = text[index + 2]
                if modrm in (0x04, 0x0C, 0x14, 0x1C, 0x24, 0x2C, 0x34, 0x3C,
                             0x00, 0x08, 0x10, 0x18, 0x20, 0x28, 0x30, 0x38):
                    counts["sgdt_sidt"] += 1
                    index += 3
                    continue
        index += 1
    return counts


def strings_present(data):
    found = {}
    for needle in PROTECTOR_STRINGS:
        hits = data.count(needle.encode())
        if hits:
            found[needle] = hits
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("exe", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--entry-code", action="store_true",
                        help="disassemble the entry point; a protector replaces it")
    args = parser.parse_args()

    data = args.exe.read_bytes()
    pe, section_list = sections(data)
    magic, image_base, entry, _, directories = optional_header(data, pe)
    text = b"".join(data[s["raw"]:s["raw"] + s["raw_size"]]
                    for s in section_list if s["exec"])

    report = {"file": args.exe.name, "bytes": len(data), "image_base": image_base,
              "entry_rva": entry, "sections": [], "idioms": {}, "protector_strings": {},
              "anti_debug_imports": [], "tls_directory": None}
    for section in section_list:
        blob = data[section["raw"]:section["raw"] + section["raw_size"]]
        report["sections"].append({
            "name": section["name"], "bytes": section["raw_size"],
            "entropy": round(entropy(blob), 3), "exec": section["exec"]})

    report["idioms"] = scan(text)
    report["protector_strings"] = strings_present(data)
    report["protector_section_names"] = [s["name"] for s in section_list
                                         if any(marker in s["raw_name"] for marker in
                                                PROTECTOR_NAMES)]

    tls_rva, tls_size = data_directory(data, directories, 9)
    callbacks = []
    offset = rva_offset(section_list, tls_rva) if tls_rva else None
    if offset is not None and tls_size >= 40:
        callback_va = struct.unpack_from("<Q", data, offset + 24)[0]
        callback_rva = callback_va - image_base
        entries = rva_offset(section_list, callback_rva) if callback_va else None
        while entries is not None and entries + 8 <= len(data):
            entry_va = struct.unpack_from("<Q", data, entries)[0]
            if entry_va == 0:
                break
            callbacks.append(entry_va - image_base)
            entries += 8
    report["tls_directory"] = {"rva": tls_rva, "size": tls_size, "callbacks": callbacks}

    # Import names, read as ASCII from the import name tables: the audit only needs the set.
    import_names = set()
    import_rva, _ = data_directory(data, directories, 1)
    offset = rva_offset(section_list, import_rva)
    if offset is not None:
        cursor = offset
        while True:
            original, stamp, chain, name_rva, first = struct.unpack_from("<IIIII", data, cursor)
            if name_rva == 0:
                break
            name_at = rva_offset(section_list, name_rva)
            if name_at is not None:
                end = data.find(b"\0", name_at)
                report.setdefault("imports", []).append(
                    data[name_at:end].decode("ascii", "replace"))
            thunk = rva_offset(section_list, original or first)
            while thunk is not None and struct.unpack_from("<Q", data, thunk)[0]:
                entry_value = struct.unpack_from("<Q", data, thunk)[0]
                if not entry_value & (1 << 63):
                    name_at = rva_offset(section_list, entry_value + 2)
                    if name_at is not None:
                        end = data.find(b"\0", name_at)
                        import_names.add(data[name_at:end].decode("ascii", "replace"))
                thunk += 8
            cursor += 20
    report["anti_debug_imports"] = sorted(name for name in import_names
                                          if name in ANTI_DEBUG_IMPORTS)
    report["import_count"] = len(import_names)

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"{args.exe.name}: {len(data):,} bytes, image base {image_base:#x}, "
          f"entry {entry:#x}")
    print("  section        bytes        entropy  exec")
    for section in report["sections"]:
        print(f"  {section['name']:<14} {section['bytes']:>10,}   {section['entropy']:5.2f}  "
              f"{'yes' if section['exec'] else ''}")
    idioms = report["idioms"]
    code_bytes = max(1, sum(s["raw_size"] for s in section_list if s["exec"]))
    print(f"  int3 {idioms['int3']:,} over {code_bytes:,} code bytes "
          f"({1000 * idioms['int3'] / code_bytes:.2f} per KiB): "
          f"{idioms['guard']:,} guard-shaped, {idioms['padding']:,} in padding runs, "
          f"{idioms['other']:,} other")
    print(f"  0F-prefix idioms (upper bounds, code sections): rdtsc {idioms['rdtsc']:,}  "
          f"cpuid {idioms['cpuid']:,}  sgdt/sidt {idioms['sgdt_sidt']:,}  "
          f"syscall {idioms['syscall']:,}")
    print(f"  protector strings: {report['protector_strings'] or 'none'}")
    print(f"  protector section names: {report['protector_section_names'] or 'none'}")
    print(f"  anti-debug imports ({len(report['anti_debug_imports'])}): "
          f"{', '.join(report['anti_debug_imports']) or 'none'}")
    print(f"  imports {report['import_count']}, TLS directory "
          f"{report['tls_directory']['rva']:#x}/{report['tls_directory']['size']}, "
          f"callbacks {[hex(c) for c in report['tls_directory']['callbacks']] or 'none'}")

    if args.entry_code:
        import subprocess
        start = image_base + entry
        result = subprocess.run(["objdump", "-d", f"--start-address={start:#x}",
                                 f"--stop-address={start + 0x100:#x}", str(args.exe)],
                                capture_output=True, text=True)
        lines = result.stdout.splitlines()
        print("  entry point:")
        for line in lines[lines.index("Disassembly of section .text:") + 1:][:24] \
                if "Disassembly of section .text:" in lines else lines[-24:]:
            print(f"    {line.strip()}")

    packed = any(section["entropy"] > 7.5 for section in report["sections"]
                 if section["exec"])
    marked = bool(report["protector_strings"] or report["protector_section_names"])
    guard_share = idioms["guard"] / max(1, idioms["int3"])
    if marked or (packed and idioms["guard"] < idioms["padding"]):
        print("  verdict: a packer/protector is indicated by the numbers above")
    elif idioms["guard"] and guard_share > 0.05:
        print(f"  verdict: no protector markers; {100 * guard_share:.1f}% of int3 are "
              f"branch-target guards, the shape of live asserts in a checked build")
    else:
        print("  verdict: nothing here indicates a commercial protector")
    return 0


if __name__ == "__main__":
    sys.exit(main())
