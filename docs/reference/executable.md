# The executable as a source

Every claim about a format here is one of three kinds: inferred from the corpus,
measured against the corpus, or **read out of the executable**. This page
is the third kind — the functions, where they live, and exactly what each one settles.

Where the bytes and the code disagreed, the code won: it corrected the script row
field order, the chunk count, and the buffer-B relationship.

## The binary

| Field | Value |
| --- | --- |
| file | `game_scarlett_master.exe` |
| size | 120,181,760 B |
| sha256 | `e95020b2fa4a721db3df59fdecf75621730ac559d8835252f6c3b658d5a08993` |
| format | PE32+ x86-64, 10 sections, image base `0x140000000` |
| build | timestamp 1794606036 → 2026-11-13 |
| provenance | `.xbld`, `.retplne`, `.voltbl` sections; imports `d3d12_xs`, `xg_xs`, `xmem`, `xapu`, `AcpHal`, `XCRDAPI`, `XboxBvhBuilder`, `Bink2Scarlett` |

It is kept in `cache/exe/` and is never committed.

## Harness

| Tool | What it does |
| --- | --- |
| `tools/pe_scan.py` | correct PE section mapping; proves negatives (`sbox` = 0 occurrences) |
| `tools/vtable_scan.py` | enumerates vtables, resolves a slot, finds which classes own an address |
| `cache/ghidra/Target.java` | decompile the function containing an address |
| `cache/ghidra/Refs.java` | references *to* an address, via Ghidra's reference manager |
| `cache/ghidra/Indirect.java` | indirect calls through a fixed structure displacement, from the *instruction stream* |

Byte-pattern scans for `call [reg+0x60]` produce thousands of false hits; the
instruction-stream version does not. Earlier scans also unpacked PE section fields in
the wrong order and searched the wrong range — `pe_scan.py` exists so that "not found
in `.text`" means what it says.

## What the executable settles

| Address | Function | What it establishes | Status |
| --- | --- | --- | --- |
| `0x141fb2600` | region reader | copies the header, mallocs `header[+4]`, reads `0x10..size`; in mode 1 also reads `header[+8]..header[+4]` | code |
| `0x1408ec210` | mount | calls `0x1428ce530`, then two passes over the entry array | code |
| `0x14087aec0` | layout dispatch | mode 0/1/2 → `0x14087af70` → `0x14087aff0` | code |
| `0x14087aff0` | arena layout | the five section offsets from `p3..p8` and `N` | code |
| `0x14087b0b0` | table setter | stores `obj+0x38` = the record array | code |
| `0x1406bd160` | entry walker | iterates `count × 16` and registers each `(u64, u32)` | code |
| `0x1428ce080` | lookup (A) | reads `p3` from `[obj+0x30]+0x1a`, records from `obj+0x38` | code |
| `0x1428ce200` | lookup (B) | tail-calls `0x144e6f780(records, p3, key16)` | code |
| `0x144e6f780` | key scan | **linear scan**, compares `u16` at each 8-byte record, returns index or `0xffff` | code |
| `0x145305880` | name hash | Murmur3 x64-128 over `tolower(name)` with `\\`→`/`, then a 16-bit id looked up in a runtime table | code |
| `0x1465b23b0` | substitution table | 256 bytes, 27 non-identity: `A..Z`→`a..z`, `\\`→`/` | code |
| `0x144083410` | script writer | the `PSIN→…→CHKS` chain, its payloads and its poisoning | code |
| `0x14087b0f0` | arena arithmetic | `count × width × unit`, aligned | code |

### The archive object, in memory

```
+0x00  vtable                    0x1462fd480, 147 slots
+0x08  file object               the stream the archive reads from
+0x18  buffer A base
+0x20  buffer A size
+0x28  arena descriptor          filled by 0x14087aff0
+0x30  pointer to buffer A       the header itself: p3 at +0x1a, p5 at +0x20
+0x38  section 1 base            p3 records of 8 bytes
```

Two facts come out of this that the corpus could not give:

1. **Buffer A *is* the arena header.** The lookup code reads `p3` and `p5` straight
   out of the copied file bytes, so the fields at `0x1a`/`0x20` are the header, not a
   parallel structure.
2. **Section 1 is a `u16`-keyed table with a linear scan.** `0x144e6f780` walks the
   records comparing a 16-bit key and returns `0xffff` for "not found". A linear scan
   only makes sense for a small table, which matches `p3 = 4..7` in the packs measured:
   section 1 is a dispatch table indexed by a small id, not a name hash table.

### The class map

`vtable_scan.py --find 0x1462fd480` locates the archive vtable independently: **147
slots**, and the two "create archive" factories are its own methods:

| slot | target | role |
| --- | --- | --- |
| `+0x018`..`+0x028` | `0x1428cd270`, `2a0`, `2e0` | lifecycle |
| `+0x3a0` | `0x140fc2530` | validity check used by the factory |
| `+0x3f8` | `0x1428ce0b0` | key lookup (`p5` path) |
| `+0x418` | `0x140fc2490` | create child archive (constructor 1) |
| `+0x420` | `0x1411a8970` | create child archive (constructor 2) |

Because both factories are methods of the archive itself, **archives nest**: each RPF
pack is mounted as its own archive over a bounded sub-stream of the parent. There is
no external owner to find, which is why every reference search for one came up empty.

### The name hash, and why JOAAT was wrong

The archive's own name hash is **Murmur3 x64-128**, not JOAAT:

```
hash = murmur3_x64_128( tolower(name) with '\' -> '/' )
```

and the 16-bit id the archive indexes by is then *looked up* in a runtime table
(`FUN_14056ec70`), so it cannot be computed from the string offline. JOAAT remains
correct for object and field names in `PSIN` — a different subsystem — but every
JOAAT-based attempt on archive entry names was aimed at the wrong function.

`tools/name_hash_game.py` implements the hash. Two things about it are now measured
rather than believed:

* **The engine confirms it.** Scanning the image for `mov r64, imm64` whose immediate
  equals a recomputed hash finds **26 sites / 11 distinct names** — `trailers`,
  `graphics`, `snow`, `bird`, `train`, `discovery`, `none`, `null`, `default`,
  `dlc_ityp_request`, `permanent_ityp_file`. A false match is expected 3 × 10⁻⁷ times,
  so these are real. `tests/test_analysis_tools.py` asserts one of them.
* **The metadata does not store them.** 147,808 candidates against 3,716,607
  front-region `u64` words gives **zero** hits — consistent with the front region
  holding ids rather than hashes.

## What the executable rules out

| Claim | Evidence |
| --- | --- |
| the metadata is AES-encrypted | zero occurrences of the forward S-box in the whole image; the single inverse S-box is CNG library code |
| the metadata is decrypted by CNG | only `OpenAlgorithmProvider` / `GenRandom` / `CloseAlgorithmProvider` are imported |
| the front region is compressed | zlib, raw deflate, lzma and bz2 all fail at the region start; the loader also copies rather than inflates |
| the "CBC" reading of the front region | identical plaintext prefixes explain the repeated-block statistic; there is no cipher call on the path |

## What it still owes us

- the stream class behind `Read` (`+0x60`), which is the only link between the file
  and the copied bytes that has not been read;
- the meaning of sections 2–5, which the layout sizes but does not describe;
- the `CHKS` tag — ten 32-bit hash candidates are already excluded;
- the script bytecode's container, which is not in a plaintext section.

Each of these is a code question with a known starting address, not a search problem.
That is the difference the executable made.
