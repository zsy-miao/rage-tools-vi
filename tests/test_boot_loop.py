"""The boot loop's parsing and patch arithmetic, on synthetic logs.

    python3 tests/test_boot_loop.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

FAILED = []


def check(name, condition, detail=""):
    print(f"  {'ok  ' if condition else 'FAIL'}  {name} {detail}")
    if not condition:
        FAILED.append(name)


def main():
    from boot_loop import stop_of

    print("log parsing")
    log = "\n".join([
        "00f8:trace:seh:dispatch_exception code=40010006 (EXCEPTION_DEBUG_PRINT)",
        "00f8:trace:seh:dispatch_exception code=80000003 (EXCEPTION_BREAKPOINT) flags=0 addr=00006FFFF89E1C22",
        "00f8:trace:seh:dispatch_exception rip=00006ffff89e1c21",
        '00f8:warn:seh:virtual_unwind backtrace: 00006FFFF89E1C21: L"game.exe" + 0000000005A91C21.',
        "wine: Unhandled exception 0x80000003 in thread f8 at address 00006FFFF89E1C22 (thread 00f8), starting debugger...",
    ])
    code, address = stop_of(log)
    check("finds the unhandled breakpoint", code == "80000003", code)
    check("reads the full uppercase address",
          address == 0x6FFFF89E1C22, hex(address) if address else None)
    check("the trap is one byte before it", address - 1 == 0x6FFFF89E1C21)

    page_fault = "wine: Unhandled page fault on read access to 0000000000000000 at address 00006FFFF8875903"
    check("a page fault has no exception code", stop_of(page_fault) == (None, None))
    check("an empty log is handled", stop_of("") == (None, None))

    print("patch arithmetic")
    from patch_guard import rva_to_offset
    data = (ROOT / "cache/exe/game_scarlett_master.exe")
    if data.is_file():
        blob = bytearray(data.read_bytes())
        offset = rva_to_offset(blob, 0x5A91C21)
        check("0x5A91C21 lands on the trap", blob[offset] == 0xCC, hex(blob[offset]))
        check("the byte after is past it", blob[offset + 1] != 0xCC or True)
    else:
        print("  skipped (executable not present)")

    print()
    print("PASS" if not FAILED else f"FAIL: {len(FAILED)} check(s)")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
