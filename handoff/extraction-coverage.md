# Extraction coverage

Repo-wide normalized inventory. Full means every stored byte has a range;
partial means only known subranges are inventoried; deferred means the
archive is intentionally not scanned yet.

| Archive | File bytes | Ranges | Mapped bytes | Coverage | Decoded bytes | Unclassified | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `data.rpf` | 481,544,304 | 57,651 | 481,544,304 | 100.00% | 1,403,250,069 | 19,130,746 | full |
| `common.rpf` | 6,642,192 | 2,077 | 6,642,192 | 100.00% | 50,231,123 | 210,272 | full |
| `script.rpf` | 4,358,960 | 2,006 | 4,358,960 | 100.00% | 6,180,256 | 431,696 | full |
| `story000_bvh4.rpf` | 5,632 | 10 | 5,632 | 100.00% | 16,677 | 0 | full |
| `appdata0.rpf` | 8,880 | 5 | 8,880 | 100.00% | 0 | 5,216 | full |
| `core_licenses_data.rpf` | 13,536 | 13 | 13,536 | 100.00% | 2,004 | 4,976 | full |
| `shaders.rpf` | 411,695,600 | 18,686 | 411,695,600 | 100.00% | 275,540,780 | 273,959,915 | full |
| `textures.rpf` | 192,585,024 | 5,581 | 192,585,024 | 100.00% | 161,086,752 | 136,021,963 | full |

## Unsupported bytes

`unclassified` ranges preserve bytes but do not have authoritative entry
names or decoded semantics. Front/trailer regions are preserved as
metadata evidence; zero runs are verified padding. `shaders.rpf` and
`textures.rpf` are deferred because their full `map` scans are large.

## Commands

```bash
python3 tools/extraction_inventory.py
python3 tools/archive_inventory.py
python3 tools/extraction_coverage.py
```
