# Rage Tools VI

RPF9 archive extraction, entry reconstruction and identifier recovery for
**GTA VI / Leonida** — built as an evidence problem, not a guessing game.

> **Goal:** enumerate every archive entry, locate its stored bytes, decode it, and
> say what it is.

## The idea in three lines

The metadata records in an RPF9 pack are unidentified, so entries are reconstructed
from the **payload**, with the metadata used only as a cross-check:

- every payload range is found by scanning and **verified by zlib checksum**;
- every pack declares an entry count `N`, so the count is an **oracle**: an entry
  model that does not reproduce `N` exactly is rejected;
- every identifier met so far is **`JOAAT(lowercase name)`**, so names are
  recoverable by vocabulary instead of by key.

Two things are now taken from the **game executable** rather than inferred: the
script metadata chunk format (read out of its writer) and the pack's front-region
layout (read out of its loader). Where the bytes and the code disagreed, the code
settled it.

Full walkthrough: **[From first principles](docs/explained.md)**.

## Results

| Area | Result |
| --- | --- |
| Corpus index | **22 archives · 4,415,868 ranges · 161.3 GB stored** — every index tiles its archive exactly |
| Corpus pass | one command indexes, fits an entry model and emits manifests for all 22 archives in **4 minutes** |
| Entry manifests | **188,298 entries** with exact boundaries across 14 archives (packs whose count verifies exactly) |
| `core_bvh4` | **1,253 of 1,261 packs** whose declared count is reproduced exactly; 109,301 entries |
| Audio | **93,344 Opus + 1,818 XMA2 + 73 ACE1** streams, zero failures; every stream reaches its declared length |
| Names | one registry of **36,952** hash→name pairs, with a flag for JOAAT collisions |
| Script metadata | chunk chain `PSIN→LSCH→LENM→LSNS→LGID→LRSC→CHKS` recovered from the writer in the executable; **1,012/1,012** records parse, and the chain lands on the last byte of every body (zero slack). 63,288 typed rows with the type word **last**, 42 % naming their property |
| Pack layout | every header field is code-confirmed; buffer A is a 0x40-byte header plus four sections sized by a formula from the binary, which fits **654/654** headers; buffer B is a suffix of buffer A, `align16(N × stride)` |
| Provenance | `handoff/` carries 114 tables with an enforced manifest — **105 generated, 4 curated, 5 legacy**, 0 unclassified |
| GPU | shader decompilation lives in its own repository, [`rdna2-spirv`](rdna2-spirv/) |

## What is solved, and what is not

**Solved.** Payload coverage and verification for the whole corpus, at 100 % union
coverage per pack; entry boundaries for 14 archives; the `core_bvh4` descriptor
format; the `ADAT` audio container including Opus, XMA2 and PCM; the script
metadata chunk format and the `PSIN` row layout; the pack front-region layout; a
merged name registry; and the archive/stream accounting above.

**Not solved, and why.** The *contents* of the metadata records are unidentified:
no 32-bit or 64-bit hash of any known name appears in them, and the loader copies
them verbatim, so any transform would have to sit in the stream's `Read` — the one
link not yet read. There are therefore still no original file names or paths;
everything is payload-derived and offset-addressed. The compiled script bytecode is
not in a plaintext section either. The executable is now in hand, so these are
code-tracing problems rather than waiting problems.

Details and the failures that led here are in [investigation.md](investigation.md);
open work is in [plan.md](plan.md).

## Checking the repository

```bash
tools/check.sh          # the full gate, see below
tools/check.sh --fast   # skip the docs build and the shader suite
```

The gate is deliberately boring and specific: every script must compile, 33
analysis assertions must pass, the generated tool index and the handoff manifest
must be current, the counts published in the docs must match the committed
artifacts, every index must tile its archive, every pack's payload window must be
covered, and the docs must build.

Tools run through **uv** (`pyproject.toml`, `uv.lock`), so their dependencies
(numpy for the XMA2 wrapper) are declared rather than assumed. Anything needing
the source archives reports `skipped` instead of failing.

## Using the names

```bash
python3 tools/name_registry.py --build            # rebuild from every name table
python3 tools/name_registry.py --lookup 0x01166164
python3 tools/name_registry.py --annotate handoff/script-bones.tsv \
    --column bone_hash --out handoff/script-bones-named.tsv
python3 tools/annotate_handoff.py                 # every handoff table at once
```

`handoff/names.tsv` is `hash, name, kind, confidence, source, also_known_as,
ambiguous`, with confidence `curated > meta > grammar > corpus > candidate`. Where
two real strings share a 32-bit JOAAT the row is marked ambiguous rather than
picking one.

## The corpus pass

```bash
tools/corpus_pass.sh /path/to/archives --entries
python3 tools/corpus_table.py
python3 tools/corpus_report.py --write docs/extraction/corpus.md
```

It indexes each `*.rpf`, fits the entry models per pack (`single`, `pairs`,
`chains`, `structs-1`, `pos-pairs`) and, with `--entries`, emits a manifest for the
unit the archive's stream/declared ratio implies. The result is
[`docs/extraction/corpus.md`](docs/extraction/corpus.md).

## Single-purpose tools

```bash
python3 tools/stream_index.py ARCHIVE --out output/index/name.tsv
python3 tools/extract_entry.py --archive A --kind zlib --start 0x0 --end 0x1000 --output out.bin
python3 tools/psin_extract.py script.rpf           # PSIN schema from the archive
python3 tools/psin_segment.py --describe 1054      # a script's records, as entries
python3 tools/awc_chunk_table.py FILE              # ADAT chunk table for any variant
python3 tools/lsns_tables.py                       # LSNS tables and record counts
```

Formats recovered from the executable have first-class readers, all runnable without
any reverse-engineering setup:

```bash
python3 tools/script_meta.py script.rpf --index output/index/script.tsv --dump 1
python3 tools/script_meta.py script.rpf --index output/index/script.tsv --verify
python3 tools/psin_blocks.py --index output/index/script.tsv --show 1
python3 tools/pack_layout.py data.rpf --offset 0        # draw one pack from its header
python3 tools/pack_extent_check.py --all                # payload windows vs the index
```

`tools/pe_scan.py` and `tools/vtable_scan.py` are the static-analysis entry points:
the first proves negatives about a PE image with a correct section map, the second
resolves a vtable slot to the classes that could be calling it.

The Rust CLI in `src/` covers inspection, pack mapping and partition work:

```bash
cargo build && target/debug/rage-tools-vi --help
```

## Layout

| Path | Purpose |
| --- | --- |
| `src/` | Rust CLI: inspect, map, packs, partition, sections, extract |
| `tools/` | Python indexing, extraction, verification, naming and format probes |
| `handoff/` | Verified manifests and measurements — see [handoff/README.md](handoff/README.md) |
| `docs/` | MkDocs Material site with Mermaid diagrams |
| `tests/` | Smoke tests over the committed data |
| `plan.md` | Live check/todo list |
| `investigation.md` | Append-only research journal |
| `rdna2-spirv/` | Submodule: RDNA2 shader decompiler (separate repository) |

## Data and paths

No game data is stored here; `*.rpf`, `output/`, `cache/`, `site/` and `target/` are
ignored. Tools take the archive directory as an argument (`SRC=/path/to/archives` in
the shell scripts), so nothing depends on where the archives are kept.

The decoded corpus is 365 GB against 161 GB stored, so extraction streams: decompress a
range, measure it, record the manifest entry, discard the bytes. Only manifests and
measurements are committed.

## Prior art and credits

| Project | What this repository uses |
| --- | --- |
| [ItsNotRexed/Leonida](https://github.com/ItsNotRexed/Leonida) | the `ADAT` layout — `tools/awc_parse.py` implements it and cites it |
| [TrinitronClient/GTA6-Asset-Info](https://github.com/TrinitronClient/GTA6-Asset-Info) | byte-level notes on `PSIN`/`LSNS` framing and the object graph |
| [dexyfex/CodeWalker](https://github.com/dexyfex/CodeWalker) | the metadata name table used as a hash vocabulary |
| [GPUOpen isa_spec_manager](https://github.com/GPUOpen-Tools/isa_spec_manager) | the machine-readable RDNA2 ISA behind `rdna2-spirv` |

Where those notes contradicted earlier conclusions, the journal
records the correction instead of quietly changing the number.

## License

MIT — see [LICENSE](LICENSE).
