# Multi-mip texture control: blocked

2026-11-21. Task #0166 asked for one texture control with a packed mip tail or
multi-mip chain. The bounded search is complete; no such control exists in the
candidate archive.

## Scope

- Archive: local `textures.rpf` (192,585,024 bytes).
- Window: every 8 MiB aligned window from `0x0` to the end.
- Probe: `tools/texture_control_probe.py --min-mips 2`, formats `0x4D` (BC3)
  and `0x62` (BC7).
- Result: **zero matching descriptor-backed textures** in all 24 windows.

The probe's existing `min_mips` check reads the descriptor mip-count byte at
system-relative `+0x3e`. It found the verified single-mip `trophy` and
`switch_jason` controls with `--min-mips 1`, so the filter path is exercised.

## Additional `data.rpf` search

The rebuilt corpus has no `output/data.rpf` extraction, so I rebuilt a bounded
copy under `/tmp`:

- `stream_index.py` on the 481,544,304-byte `data.rpf`: 28,509 zlib streams /
  1,403,250,069 decoded bytes.
- `bulk_extract.py` to `/tmp/data-rpf/decoded`.
- `native_texture_scan.py`: **73 valid dictionaries / 788 textures**.
- `texture_control_probe.py --min-mips 2` over every unique dictionary start,
  formats `0x4D` and `0x62`: **zero hits**.

This confirms the missing multi-mip control is not hiding in `data.rpf` either.

## Status

Packed mip-tail placement, mip ordering, and multi-mip pitch remain open.
Reopen with a source window/dictionary that has a descriptor mip-count >= 2;
do not infer a tail from the single-mip controls. The known control formulas
(BC3/BC7 128-bpp swizzle, 4 KiB page grid) are unchanged.

## Reproduce

```sh
A=textures.rpf
for fmt in 0x4d 0x62; do
  for ((s=0; s<$(stat -c %s "$A"); s+=0x800000)); do
    python3 tools/texture_control_probe.py "$A" --start "$(printf '0x%x' $s)" \
      --bytes 0x800000 --format "$fmt" --min-mips 2
  done
done
```
