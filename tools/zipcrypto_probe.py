"""Test passwords against a ZipCrypto entry without extracting anything.

Traditional PKZIP encryption is a 12-byte header followed by the deflated data,
encrypted with a keystream from three CRC-derived keys. The header's last byte is a
check value — the high byte of the CRC, or of the DOS time when the data-descriptor
bit (flag bit 3) is set — so a candidate password can be tested from the header alone.

    python3 tools/zipcrypto_probe.py ZIP --wordlist FILE
    python3 tools/zipcrypto_probe.py ZIP --words cybeerleek gta6 leonida
"""
import argparse
import struct
import sys
import zlib

MASK = 0xFFFFFFFF


def keys_for(password):
    k0, k1, k2 = 0x12345678, 0x23456789, 0x34567890
    for byte in password:
        k0 = (zlib.crc32(bytes([byte]), k0 ^ MASK) ^ MASK) & MASK
        k1 = (k1 + (k0 & 0xFF)) & MASK
        k1 = (k1 * 134775813 + 1) & MASK
        k2 = (zlib.crc32(bytes([(k1 >> 24) & 0xFF]), k2 ^ MASK) ^ MASK) & MASK
    return k0, k1, k2


def decrypt_byte(k2):
    temp = (k2 | 2) & 0xFFFF
    return ((temp * (temp ^ 1)) >> 8) & 0xFF


def entry(path, index=0):
    data = open(path, "rb").read()
    eocd = data.rfind(b"PK\x05\x06")
    count, _, offset = struct.unpack_from("<HII", data, eocd + 10)
    position = offset
    for i in range(count):
        need, flags, method = struct.unpack_from("<HHH", data, position + 6)
        dostime, dosdate = struct.unpack_from("<HH", data, position + 12)
        crc, csize, usize, nlen, elen, clen = struct.unpack_from(
            "<IIIHHH", data, position + 16)
        local = struct.unpack_from("<I", data, position + 42)[0]
        name = data[position + 46:position + 46 + nlen].decode(errors="ignore")
        if i == index:
            # the local header repeats the name and extra fields; data follows
            l_nlen, l_elen = struct.unpack_from("<HH", data, local + 26)
            start = local + 30 + l_nlen + l_elen
            return {"name": name, "flags": flags, "method": method, "crc": crc,
                    "csize": csize, "usize": usize, "dostime": dostime,
                    "header": data[start:start + 12], "data_offset": start}
        position += 46 + nlen + elen + clen
    raise SystemExit(f"index {index} out of range")


def check(password, info):
    k0, k1, k2 = keys_for(password)
    last = 0
    for cipher in info["header"]:
        plain = cipher ^ decrypt_byte(k2)
        k0 = (zlib.crc32(bytes([plain]), k0 ^ MASK) ^ MASK) & MASK
        k1 = (k1 + (k0 & 0xFF)) & MASK
        k1 = (k1 * 134775813 + 1) & MASK
        k2 = (zlib.crc32(bytes([(k1 >> 24) & 0xFF]), k2 ^ MASK) ^ MASK) & MASK
        last = plain
    expected = ((info["dostime"] >> 8) & 0xFF) if info["flags"] & 0x08 else (info["crc"] >> 24)
    return last == expected


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("zip")
    parser.add_argument("--wordlist")
    parser.add_argument("--words", nargs="*")
    parser.add_argument("--index", type=int, default=1)
    args = parser.parse_args()

    info = entry(args.zip, args.index)
    print(f"entry {info['name']}: flags=0x{info['flags']:04x} "
          f"method={info['method']} crc=0x{info['crc']:08x}")
    candidates = []
    if args.words:
        candidates += [w.encode() for w in args.words]
    if args.wordlist:
        candidates += [line.rstrip(b"\r\n") for line in open(args.wordlist, "rb")]
    tested = 0
    for password in candidates:
        if not password:
            continue
        tested += 1
        if check(password, info):
            print(f"PASSWORD: {password.decode(errors='replace')}  (after {tested} tries)")
            return 0
    print(f"no match in {tested} candidates")
    return 1


if __name__ == "__main__":
    sys.exit(main())
