"""Parse the `0xff02` / `0xff25` AWC variants and report their codecs.

The `audio.rpf` container (`0xff21`) was already parsed by `awc_framing.py`. The
`story000` chain is 98 % `0xff02`, whose layout differs:

    0x00  ADAT
    0x04  u16 version, u16 flags (0xff02)
    0x08  u32 stream count
    0x0c  u32 data offset
    0x10  4 * streams bytes (per-stream, content unknown)
         chunk table, 8-byte records, ending at the data offset
         record = offset:28 | size:28 | type:8   (little-endian u64)

Each stream owns exactly seven chunks: `0x36 0x55 0x5c 0x76 0xa3 0xb2 0xbd`, so
`data_offset = 16 + 4n + 56n = 16 + 60n`. The `0x76` chunk is the 32-byte
descriptor: sample count at `+0x00`/`+0x0c`, rate at `+0x08`, codec at `+0x1c`,
codec sub-ID at `+0x1d`. The `0x55` chunk is the data.

This tool validates that model across a sample and reports the codec mix, which
is what a decoder needs before any bulk decode.
"""

import argparse
import csv
import random
import struct
from collections import Counter
from pathlib import Path

TYPES = (0x36, 0x55, 0x5C, 0x76, 0xA3, 0xB2, 0xBD)


def parse_ff02(data):
    streams, data_offset = struct.unpack_from("<II", data, 0x08)
    table = 0x10 + 4 * streams
    count = (data_offset - table) // 8
    chunks = []
    for index in range(count):
        value = struct.unpack_from("<Q", data, table + 8 * index)[0]
        chunks.append({"offset": value & 0x0FFFFFFF,
                       "size": (value >> 28) & 0x0FFFFFFF,
                       "type": (value >> 56) & 0xFF})
    return streams, data_offset, chunks


def describe(data):
    streams, data_offset, chunks = parse_ff02(data)
    per_stream = [chunks[i * len(TYPES):(i + 1) * len(TYPES)] for i in range(streams)]
    out = {
        "streams": streams,
        "data_offset": data_offset,
        "chunks": len(chunks),
        "seven_per_stream": all(len(group) == len(TYPES) for group in per_stream),
        "type_order_ok": all([c["type"] for c in group] == list(TYPES) for group in per_stream),
    }
    first = per_stream[0] if per_stream else []
    by_type = {chunk["type"]: chunk for chunk in first}
    desc = by_type.get(0x76)
    payload = by_type.get(0x55)
    if desc and desc["offset"] + desc["size"] <= len(data):
        body = data[desc["offset"]:desc["offset"] + desc["size"]]
        if len(body) >= 0x20:
            # Rate is the low u16 at +0x08 (0xBB80 = 48 kHz); the high u16 is a
            # count, so reading a u32 here yields nonsense for both variants.
            out["rate"] = struct.unpack_from("<H", body, 0x08)[0]
            out["num0"] = struct.unpack_from("<I", body, 0x00)[0]
            out["num1"] = struct.unpack_from("<I", body, 0x0C)[0]
            out["codec"] = body[0x1C]
            out["subcodec"] = body[0x1D]
    if payload:
        out["data_offset_in_file"] = payload["offset"]
        out["data_size"] = payload["size"]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sample", type=int, default=400)
    parser.add_argument("--tsv", type=Path, default=Path("handoff/story000-awc-variants.tsv"))
    args = parser.parse_args()

    rows = list(csv.DictReader(args.manifest.open(), delimiter="\t"))
    random.seed(0xA3)
    picked = random.sample(rows, min(args.sample, len(rows)))
    flags = Counter()
    codecs = Counter()
    rates = Counter()
    ok = 0
    rows_out = []
    for row in picked:
        data = Path(row["path"]).read_bytes()
        family = struct.unpack_from("<H", data, 6)[0]
        flags[hex(family)] += 1
        if family not in (0xFF02,):
            continue
        info = describe(data)
        if info.get("seven_per_stream") and info.get("type_order_ok"):
            ok += 1
        info["path"] = row["path"]
        info["flags"] = f"0x{family:04x}"
        rows_out.append(info)
        if "codec" in info:
            codecs[hex(info["codec"])] += 1
            rates[info.get("rate")] += 1

    print(f"sampled {len(picked)} containers")
    print("flag families:", dict(flags))
    print(f"0xff02 parsed with 7 ordered chunks per stream: {ok}")
    print("codecs:", dict(codecs))
    print("rates:", dict(rates))

    fields = ["path", "flags", "streams", "data_offset", "chunks", "seven_per_stream",
              "type_order_ok", "codec", "subcodec", "rate", "num0", "num1",
              "data_offset_in_file", "data_size"]
    args.tsv.parent.mkdir(parents=True, exist_ok=True)
    with args.tsv.open("w") as out:
        writer = csv.DictWriter(out, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows_out:
            writer.writerow({field: row.get(field, "") for field in fields})
    print(f"wrote {args.tsv}")


if __name__ == "__main__":
    main()
