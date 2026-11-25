# BC3 and swizzle check on the trophy texture

Bus handoff #0160, 2026-11-21. The `64×64` `trophy` control decodes to a
coherent RGBA PNG with BC3 and the low 4 KiB of the published 2D 128-bpp
standard swizzle.

## Source and descriptor

The control is an existing one-texture dictionary in local `textures.rpf`.
Both archive-relative ranges inflate exactly and pass their zlib checksums.

| Range | Role | Decoded bytes |
| --- | --- | ---: |
| `0x9160010..0x916006b` | System and descriptor | 240 |
| `0x9160070..0x91603ae` | Graphics | 4,096 |

The dictionary's name hash `0xd412c697` matches `trophy`. Its system-relative
descriptor starts at `0x40`.

| Descriptor-relative field | Value |
| --- | --- |
| `+0x08` u32 block count | 256 |
| `+0x0c` u16 block stride | 16 bytes |
| `+0x0e` u16 kind | 8 |
| `+0x10` u64 flags | `0x980` |
| `+0x18` u64 graphics pointer | `0x60000000`, graphics-relative 0 |
| `+0x38..+0x3e` u16 width, height, depth | 64, 64, 1 |
| `+0x3e` byte | 1, consistent with one mip |
| `+0x3f` format byte | `0x4d` |

Microsoft's DXGI enum assigns `0x4d` to BC3 UNORM and `0x62` to BC7 UNORM.
The BC3 top mip needs exactly `16 × 16 × 16 = 0x1000` bytes, which consumes
this graphics buffer from offset zero. After reordering, the linear pitch
is `0x100` bytes per row of BC3 blocks. The on-disk order within this tile
uses the address equation below. [DXGI format enum](https://learn.microsoft.com/en-us/windows/win32/api/dxgiformat/ne-dxgiformat-dxgi_format)

## Block order

With block coordinates `x` and `y` in `0..15`, from the graphics pointer:

```text
byte_offset = deposit_bits(16 * x, 0xaacf) | deposit_bits(y, 0x5530)
```

`deposit_bits` places the low bits of its value into the selected mask bits in
ascending order. The probe tested all 40,320 permutations of the eight block
address bits. The unique best result placed the low-to-high `x` bits at block
address positions `2,3,5,7` and the `y` bits at `0,1,4,6`. All 256 block
addresses independently match the published 128-bpp pattern within the first
4 KiB. [D3D12 swizzle formula and pattern](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ne-d3d12-d3d12_texture_layout#remarks)

Across adjacent blocks, mean absolute premultiplied RGBA seam delta is
10.9012 for the recovered order, 13.5301 for the next-best permutation,
54.0775 for 4×4 row-major block tiles, and 86.3884 for linear order. Visual
inspection shows a continuous striped circle with transparent corners.
This control leaves multi-tile pitch, packed mip tails, and a `0x62` decode
open.

## Reproduce

```sh
python3 -B tools/texture_control_probe.py textures.rpf \
  --start 0x9160010 --bytes 0x1000 --name trophy --address-bits \
  --png-out output/texture-control/trophy.png
sha256sum output/texture-control/trophy.png
```

- Graphics buffer SHA-256 `cf5a1f149889a4ad214ae0bb6aedbc8ead96dd470db300efb69714bb61e63836`
- PNG SHA-256 `11e6b167e57576cabe140fd5740b1d31a2d5d04659687101e2a997b29e71d38e`
