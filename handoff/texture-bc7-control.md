# BC7 and page layout check on switch_jason

Bus handoff #0163, 2026-11-21. The `172×172` `switch_jason` texture decodes
as BC7 with row-major 4 KiB pages and the previously verified 128-bpp swizzle
inside each page.

## Source evidence

The checksum-verified zlib streams in local `textures.rpf` form a
two-texture dictionary. Ranges are archive-relative and end-exclusive.

| Range | Role | Decoded bytes |
| --- | --- | ---: |
| `0x9158010..0x915808d` | System and descriptors | 400 |
| `0x9158090..0x915c098` | Graphics chunk 1 | 65,536 |
| `0x915c0a0..0x915fcd3` | Graphics chunk 2 | 36,864 |

`switch_jason` reproduces JOAAT `0x42004f53`. Its system-relative descriptor
at `0x40` gives the following values.

| Descriptor field | Value |
| --- | --- |
| `+0x08` block count | `0x900` |
| `+0x0c` block stride | 16 bytes |
| `+0x0e` kind and `+0x10` flags | 8 and `0x980` |
| `+0x18` graphics pointer | `0x60000000` |
| `+0x38`, `+0x3a`, `+0x3c` dimensions | 172, 172, 1 |
| `+0x3e` mip-count byte | 1 |
| `+0x3f` format byte | `0x62` |

The first texture occupies graphics-relative `0..0x9000` from mip offset
zero. Its buffer SHA-256 is
`cf3a53bb9ed75969372d7b74bcc96295633f93b495b22916f91c711256fe67cc`.
The format value matches DXGI BC7 UNORM. [DXGI format enum](https://learn.microsoft.com/en-us/windows/win32/api/dxgiformat/ne-dxgiformat-dxgi_format)

## Addressing and validation

The active image is `43×43` BC blocks. The descriptor allocates a
`48×48` block grid, exactly nine `16×16` pages at `0x1000` bytes each.
For block coordinates `x` and `y` in `0..42`, the byte address relative to
the graphics pointer is:

```text
page = 3 * (y // 16) + (x // 16)
address = 0x1000 * page
          + deposit_bits(16 * (x % 16), 0xaacf)
          + deposit_bits(y % 16, 0x5530)
```

`deposit_bits` places low input bits into the chosen mask bits in ascending
order. The within-page masks are the ones independently verified on
`trophy`. The physical page-row stride is `0x3000` bytes per 16 block
rows. The logical linear pitch after detiling and cropping is 688
bytes per block row. [Trophy control](texture-trophy-control.md)

All 1,849 selected blocks have a defined BC7 mode prefix. The mode counts
from 0 through 7 are `18, 530, 6, 58, 43, 897, 201, 96`. All 455 omitted
blocks are all-zero padding. Pillow's BC7 decoder renders the expected
coherent portrait. [BC7 mode reference](https://learn.microsoft.com/en-us/windows/win32/direct3d11/bc7-format-mode-reference)

| Order | Mean seam delta | Delta across page seams |
| --- | ---: | ---: |
| Row-major pages | 5.2591 | 13.4262 |
| Compact Morton pages | 7.4762 | 60.6301 |
| Column-major pages | 9.8603 | 95.6130 |
| Tight linear | 34.1674 | 19.6483 |
| Padded linear | 36.8412 | 45.5320 |

The scores are mean absolute differences of adjacent premultiplied RGBA
samples across block and 64-pixel page boundaries. The result validates
this one multi-page, single-mip control. Packed mip tails and other
descriptor modes remain open.

## Reproduce

```sh
python3 -B tools/texture_control_probe.py textures.rpf \
  --start 0x9158010 --bytes 0x8000 --format 0x62 --name switch_jason \
  --png-out output/texture-control/switch_jason.png
sha256sum output/texture-control/switch_jason.png
```

The BC7 path uses Pillow. PNG SHA-256 is
`897556fdc95e6718b5a5560d32a9d21dafdb408552288a5926c9c2da251cf8a6`.
