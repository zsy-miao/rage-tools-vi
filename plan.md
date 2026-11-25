# Plan

Live check/todo list. Evidence, measurements and the failures that led here belong in
[investigation.md](investigation.md) and `handoff/`; completed work is one line of state,
not a log.

Last updated: 2026-11-24.

## Current state

- **Corpus:** 22 archives indexed — 4,415,868 ranges / 161.3 GB stored / 365.0 GB
  decoded; every index tiles its archive (28 tables in `output/index`).
- **Audio:** 70,484 containers / 1,819,816 streams. The `0xff25` corpus decodes to 3,008
  WAVs / 100.96 h; the other variants run through the table rules.
- **Script schema:** 1,012/1,012 records parse the seven-chunk chain; 63,288 typed rows,
  42 % of them with a named property.
- **Names:** 36,952 hash→name pairs with confidence; 4.3 % of hash values named.
- **Tests:** `tools/rage.py test --tier unit|corpus|all`; the gate is
  `tools/check.sh`, which also runs `cargo test` and the docs build.
- **Executable:** console image (`xg_xs`, `d3d12_xs`, `xapu`, `xmem`, `AcpHal`,
  `XCRDAPI`, `XboxBvhBuilder`, `Bink2Scarlett`); `tools/rage.py play` classifies it.

## Open

- [ ] Settle whether the typed row's `c` word is a declaration index or a value.
- [ ] Identify the `CHKS` tag.
- [ ] Explain the 36.7 % partial match on the `LSCH` `+0x18` word.
- [ ] Identify the roles of `0x01393259`, `0x16` and `0xaeb623d8`.
- [ ] Find the second component's size law in the 440 composite packs.
- [ ] Identify what the two loaded ranges contain: section 1 is `align16(p3*8)` bytes at
  `obj[+0x10]`, section 2 is `p4 - header[0x30]` bytes at `obj[+0x18]`, both hashed
  content; and reconcile the arena's last term with the measured region sizes.
- [ ] Decode the remaining ~1.7 M Opus streams.
- [ ] Carve the shader programs — the boundary has to come from the loader's table or from
  the streams the index already finds.
- [ ] Content check for every decode path (flatness for audio, pixel stats for images,
  frames against declared for video).
- [ ] ACE1 trailer pairs (15 `u32` fields, 73 streams).
- [ ] Map the script type/class IDs and transforms.
- [ ] Resolve the unnamed object roots.
- [ ] Script object root field roles.
- [ ] Packs active-learning queue.
- [ ] Give `levels` an entry model (728 of 2,044 packs exact).
- [ ] Name the remaining ped-rig bones and weight hashes.

## Candidates on the boot thread

Each line is a route, what would settle it, and where it stands.

- [ ] **Frames.** `tests/test_boot_frames.py` is the scoreboard, and it is literal: a real
  window on the session display, content frames, then a static screen after the videos. It
  reports no window at all; the unpatched image stops on the first guard
  (`image+0x2237178`) inside a second. Settle by finding what should fill the object field
  that guard tests (`obj+0xc`), which is zero from the constructor at `image+0x582a610`.
- [ ] **The startup barrier is signalable.** The main thread creates two auto-reset events and
  one manual-reset event (`04ec` in Wine's server log) and waits infinite on the manual one.
  Signalling it (`STUB_EVENT_KICK=<ms>`) makes the engine create 16 worker threads and run game
  code; it then faults ~8,100 times, 543 of which are one write through a NULL allocator
  result at `image+0x554bdcb`. Settle by finding what signals that event on the platform, then
  why the engine's allocator returns NULL once its threads run.
- [ ] **The four port pieces, in order.** Each comes from the public harness
  `OnlyMoisties/GTA6-BootTest`, which reaches this build's first UI screen on Windows:
  (1) `xmem` with a GPU-visible pool mapped through vkd3d plus the `G:` package-root
  redirect (the drive now exists in the prefix; the hook is what the harness does);
  (2) `d3d12_xs` as real COM device/queue/command-list objects with `PresentX`, forwarding
  entry points to the prefix's `d3d12.dll`; (3) `XCRDAPI` as a factory with a synchronous
  DirectStorage queue over zlib-deflated ranges; (4) `rdna2-spirv` wired as the shader
  translator at dispatch. Check each with `tests/test_boot_frames.py --compare-frame`
  against the package's `xbs_splash.png`.
- [ ] **Frames.** Zero. The image stays alive, samples three threads for its whole life, and
  waits infinite on a count-0 semaphore (`image+0x56a0d`); `D3D12XboxCreateDevice` is never
  called. The public harness `OnlyMoisties/GTA6-BootTest` reaches this build's first UI screen
  on Windows with a GPU-visible pool, `d3d12_xs` device objects with `PresentX` and a
  synchronous DirectStorage queue; that port is the remaining work.
- [ ] **Crash reporter.** It posts minidumps to `submit.backtrace.io`; the frames test now
  runs inside `unshare -rn` so nothing leaves the machine. Settle nothing further unless a
  run needs the network, which is `--online`.
- [ ] **The guard at `image+0x2237178`.** It fires with the reporter registered, with `T:`
  present, with a real `d3d12_xs`, and after the arena fix. Its early exit is a failed lookup
  in the container at `image+0x56eb30` for `L"D:\LocalDumps"`, which the image never asks the
  filesystem for. Settle by reading the container's fill site and the value it wants.
- [ ] **Title and sandbox answers.** The crash context reports `TitleID: unknown`,
  `Sandbox: unknown`, `System Language: Unknown State` in `System Init`, while
  `MicrosoftGame.Config` in the package carries `7952987A`.
  Settle by answering that query from the config and seeing the fields filled in the next
  crash log; the package's own `microsoft_gameconfig.bin` has the same values in GDK form.
- [ ] **The abort after five guards.** With the five guards patched the image raises no
  breakpoint and dies in the CRT (`VCRUNTIME140+0x1989`, handler `_XcptFilter` returns 1).
  Settle by identifying the uncaught exception that reaches that path — the frames read
  `0x2240EFC <- 0x81B253 <- 0x53EC04F <- 0x53EBF3A <- 0x661F0`, all inside the image.
- [ ] **The `_xs` shim is written, not exercised.** `tools/d3d12_xs.c` forwards the
  root-signature and device entry points to vkd3d-proton, but no run has called
  `D3D12XboxCreateDevice`: the only `d3d12_xs` call reached so far is
  `D3D12ConfigureVirtualMemoryX`, before the first guard. Settle by reaching the create
  call in a run and reading the device it returns.
- [ ] **Five guards walked.** `image+0x2237178`, `+0x2224517`, `+0x1d5cc69`, `+0x22106e0`,
  `+0x2219650` are bypassed in one unattended run; the next stop is a write to 0 inside a
  system library. Settle by identifying which argument the image passes before that call.
- [ ] **GameInput creation.** `FUN_1459258a0` lazily creates the interface through the
  ordinal-1 import and caches it in `image+0x9ab15e8`; with the stubs loaded the create is
  called and execution stops at `image+0x592591B` reading `0xFFFFFFFFFFFFFFFF`. Settle by
  reading what the image stores next to that global before releasing the old object.
- [ ] **Interface layouts.** Six GUIDs, slot 2 called as `(object, buffer, 0x20)`. Settle by
  decompiling the callers at `+0x55DEB6E` and `+0x55DE0xx`, which read the returned fields.
- [ ] **Stream class.** The archive ctor passes `stream+0x10/+0x18/+0x20` into the region
  reader. Settle by decompiling the class and its `Read` at `+0x60`; this also unblocks the
  RPF9 table of contents.
- [ ] **PC build.** `tools/rage.py play` re-classifies any image; a PC build removes the
  whole GDK surface. Settle by pointing the tool at one.
- [ ] **Recompilation project.** Its runtime is the same surface done once; settle by
  comparing its interface expectations with the six GUIDs.

## Status of the boot thread

No window has ever opened, and the window is a proxy, not the goal: what the project is
for is knowing what every byte of these archives is, with claims that hold up. On that
measure the boot thread has produced a map (which libraries the image needs, which guards
fire, which interfaces it queries) and nothing that runs. `tests/test_boot_frames.py`
reports `lit 0.0 %`, and the process exits in under a second.

## Running the game

Static recompilation of the console image, on the user's own copy: the CPU is x86-64, so
the code runs natively once the console system software is reimplemented, and the
precompiled RDNA2 programs are translated to SPIR-V. This repository is the
reverse-engineering side of that effort — the RPF9 layout and index, and `rdna2-spirv/`
for the translation step. Hand-written stubs for the GDK surface stay off this path
(parked, see `AGENTS.md`).

## Blocked

Each needs a specific input, not more effort.

- [ ] Play the game: needs a PC build, or the console system software implemented by a
  recompilation project. Guard patching moves the stop but not the requirement, and the
  unattended loop needs its backtrace parser fixed first (`tools/boot_loop.py`).
- [ ] RPF9 table of contents: content unidentified. `Front B` is a per-entry table for 206
  of 654 packs and composite for the other 448, and neither joaat, the 64-bit families nor
  the engine's own Murmur3 x64-128 (both halves, 41,550 values, zero hits) appear in it.
- [ ] Read the stream class: its `Read` at `+0x60`, and the three words at `+0x10`,
  `+0x18`, `+0x20` that the archive ctor passes to the region reader.
- [ ] Front A milestone on `story000_bvh4.rpf` — needs independent table framing.
- [ ] Exact end of the last `data.rpf` child — needs an independent trailer start.
- [ ] Multi-mip texture tail — needs a multi-mip dictionary.
- [ ] The 331,728-byte `script.rpf` blob — not any single range in the index.
- [ ] Script bytecode container — a code-tracing task.
- [ ] Type-name vocabulary (`root_type`, `type_tag`).
