"""Robustness: the parsers must return on arbitrary bytes, never raise.

Real archives are well-formed. Bytes from a partly downloaded file, a modded range, or a
wrong offset are not. A parser that raises on garbage makes every caller responsible for
guessing whether the input was valid; a parser that returns an empty or negative result
lets the caller decide with the same evidence the parser had.

    python3 tests/test_robustness.py [--rounds N]
"""

import argparse
import random
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

FAILED = []


def check(name, condition, detail=""):
    print(f"  {'ok  ' if condition else 'FAIL'}  {name} {detail}")
    if not condition:
        FAILED.append(name)


def buffers(rounds, seed=1234):
    rng = random.Random(seed)
    sizes = [0, 1, 2, 3, 7, 16, 63, 0x800, 0x801, 4096, 0x10000]
    for size in sizes:
        yield bytes(rng.getrandbits(8) for _ in range(size))
    for _ in range(rounds):
        size = rng.choice([rng.randrange(0, 64), rng.randrange(0, 0x3000)])
        yield bytes(rng.getrandbits(8) for _ in range(size))


def structured(rng):
    """Inputs that look plausible to the shallow checks but are still wrong."""
    blob = bytearray(rng.randrange(0, 0x4000))
    for offset in range(0, len(blob), 0x800):
        if rng.random() < 0.5:
            struct.pack_into("<H", blob, offset, rng.randrange(1, 1276))
    return bytes(blob)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=200)
    args = parser.parse_args()

    from decode_adat_stream import ff25_auto, ff25_packets, ff25_packets_auto
    from script_meta import solve_count, chunk_header

    rng = random.Random(99)
    inputs = list(buffers(args.rounds)) + [structured(rng) for _ in range(20)]

    print("ff25 framing")
    for blob in inputs:
        try:
            packets = ff25_packets_auto(blob)
            phase, count = ff25_auto(blob)
        except Exception as error:  # noqa: BLE001 - the point is that it cannot happen
            check("phase search survives arbitrary bytes", False, repr(error))
            break
        if not (0 <= phase < 0x800 and count == len(packets)):
            check("phase search returns a consistent phase", False, (phase, count, len(packets)))
            break
    else:
        check("phase search survives arbitrary bytes", True, f"({len(inputs)} inputs)")
        check("phase search returns a consistent phase", True)

    print("script metadata")
    for blob in inputs:
        try:
            chunk_header(blob, 0)
            solve_count(blob, 0)
        except Exception as error:  # noqa: BLE001
            check("chain solver survives arbitrary bytes", False, repr(error))
            break
    else:
        check("chain solver survives arbitrary bytes", True, f"({len(inputs)} inputs)")

    print("ADAT bank walk")
    from io import BytesIO
    from adat_index import bank_extent
    for blob in inputs:
        try:
            end, count, tags, variant, error = bank_extent(BytesIO(blob), 0)
        except Exception as failure:  # noqa: BLE001
            check("bank walk survives arbitrary bytes", False, repr(failure))
            break
        if end is not None and not (count and 0 <= end <= len(blob) + 0x1000):
            check("an accepted bank has a bounded extent", False, (end, count))
            break
    else:
        check("bank walk survives arbitrary bytes", True, f"({len(inputs)} inputs)")
        check("a rejected bank carries a reason", all(
            bank_extent(BytesIO(blob), 0)[4] for blob in inputs[:5]), "")

    print("Bink2 header")
    from bink_index import movie_at
    for blob in inputs:
        try:
            end, fields, error = movie_at(BytesIO(blob), 0, len(blob))
        except Exception as failure:  # noqa: BLE001
            check("bink header survives arbitrary bytes", False, repr(failure))
            break
        if end is not None and not (end <= len(blob) and fields):
            check("an accepted movie has a bounded extent", False, (end, fields))
            break
    else:
        check("bink header survives arbitrary bytes", True, f"({len(inputs)} inputs)")

    print("bounded output")
    huge = b"\xff" * 0x20000
    packets = ff25_packets_auto(huge)
    check("a repeated 0xff buffer yields no packets", packets == [], len(packets))
    packets = ff25_packets(huge)
    check("the fixed-phase walk also returns nothing", packets == [], len(packets))

    print()
    print("PASS" if not FAILED else f"FAIL: {len(FAILED)} check(s)")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
