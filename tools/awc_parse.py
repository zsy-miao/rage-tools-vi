"""Parse an `ADAT` bank, following the published GTA VI audio layout.

The layout is not ours: it comes from the format notes and the `awc_opus.py`
implementation in ItsNotRexed/Leonida, and `TrinitronClient/GTA6-Asset-Info`
documents the same fields. Two details in particular are theirs and were wrong
here first:

  * the per-stream word is `id:29 | tag_count:3` — the count is the **high** three
    bits, not the low three;
  * `flags` at 0x04 selects optional tables (0x400000, 0x10000, 0x200000), and when
    the 0x10000 table is present its entries are the cumulative tag index per
    stream, which is a free consistency check.

    streams, music = parse(open("bank.awc","rb").read())
"""
import struct

TAG_DATA, TAG_FORMAT, TAG_MUSIC = 0x55, 0x76, 0x48


def parse(data):
    """Return (streams, music). Raises ValueError on an inconsistent bank."""
    if data[:4] != b"ADAT":
        raise ValueError("not a little-endian ADAT bank")
    flags, count, header_size = struct.unpack_from("<III", data, 4)
    position = 16 + (4 if flags & 0x400000 else 0)
    index_at = position if flags & 0x10000 else -1
    if index_at >= 0:
        position += count * 2
    if flags & 0x200000:
        position += (count + 1) * 4
    info = position
    position += count * 4

    streams, music = [], []
    tags_seen = 0
    for index in range(count):
        word = struct.unpack_from("<I", data, info + 4 * index)[0]
        stream_id, tag_count = word & 0x1FFFFFFF, word >> 29
        if index_at >= 0:
            expected, = struct.unpack_from("<H", data, index_at + 2 * index)
            if expected != tags_seen:
                raise ValueError(f"index entry {index} != cumulative tag count")
        tags_seen += tag_count
        body = fmt = mus = None
        for _ in range(tag_count):
            tag = struct.unpack_from("<Q", data, position)[0]
            position += 8
            kind, size, offset = tag >> 56, (tag >> 28) & 0x0FFFFFFF, tag & 0x0FFFFFFF
            if kind in (TAG_DATA, TAG_FORMAT, TAG_MUSIC) and offset + size > len(data):
                raise ValueError(f"tag 0x{kind:02x} extends outside the bank")
            if kind == TAG_DATA:
                body = (offset, size)
            elif kind == TAG_FORMAT:
                fmt = (offset, size)
            elif kind == TAG_MUSIC:
                mus = (offset, size)
        if mus and body:
            music.append((mus, body))
        if body and fmt and fmt[1] >= 32:
            samples, = struct.unpack_from("<I", data, fmt[0])
            rate, = struct.unpack_from("<H", data, fmt[0] + 8)
            codec, channels = data[fmt[0] + 28], data[fmt[0] + 29]
            frames = (struct.unpack_from("<I", data, fmt[0] + 12)[0]
                      if codec == 0x0B and fmt[1] >= 16 else 0)
            streams.append({"id": stream_id, "samples": samples, "rate": rate,
                            "codec": codec, "channels": channels,
                            "frames": frames, "data": body})
    return streams, music


def opus_packets(data, at, size):
    """Packets from 2048-byte blocks of `[u16 length][packet]`, zero padded."""
    out = []
    for block in range(at, at + size, 2048):
        position = block
        end = block + 2048
        while position + 2 <= end:
            length, = struct.unpack_from("<H", data, position)
            if length == 0 or position + 2 + length > end:
                break
            out.append(bytes(data[position + 2:position + 2 + length]))
            position += 2 + length
    return out
