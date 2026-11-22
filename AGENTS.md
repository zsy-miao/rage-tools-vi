# Rage Tools VI investigation

Working agreements for this repository. New standing instructions from the operator
are appended here.

## Standing directives

- 2026-11-20: Save every working analysis script in `tools/`. Do not leave a
  successful one-off script only in shell history or an inline heredoc.
- 2026-11-20: Keep the roadmap, todo, and current state in `plan.md`.
  `investigation.md` is an append-only journal; append new evidence at the end
  instead of rewriting existing entries.
- 2026-11-20: When a task could use two Codex sessions and the mode is unclear,
  ask the operator whether this is a dual-session run before setting up the second
  workstream. If the operator already chose the mode, proceed with that choice.
- 2026-11-20: In dual-session mode, both sessions keep their turns open and
  wait on the bus between and after handoffs until the operator interrupts or ends
  the run.
- 2026-11-20: In dual-session standby, block on an inotify subscription to
  the bus directory. Keep that subscriber alive when the harness yields.
- 2026-11-20: Negotiate acknowledgment, progress, and result timing per
  bus message when needed.
- 2026-11-20: The lead waits up to five minutes for acknowledgment of an
  active handoff. If none arrives, record `NO_ACK` for that handoff once.
  This is a lead-side deadline. The worker starts when they receive the work.
- 2026-11-21: Bus `wait` defaults to at most 1 second. Do not use long
  timeouts; poll in a loop and answer immediately when a message arrives.
- 2026-11-21: `investigation.md` holds the research record; append evidence
  as dated entries. `plan.md` is only the live check/todo list — do not record
  findings, tool tables, or completed-work lists there.
- 2026-11-21: exploration copies may live on the local NVMe inside the repo
  (untracked `cache/`), not only on the Mammoth volume. Keep archive slices,
  decoded samples, and analysis caches local when re-reading the source would
  cost minutes; never commit them.
- 2026-11-22: The operator has licensed, NDA-approved access to Microsoft
  (Dev Center / Partner) material, including GDK headers. Any such material is
  local-only: keep it outside git (`.gitignore` covers `private/`; the
  `rdna2-spirv` submodule ignores its own `private/`), never commit it, never
  paste it into docs, journals,
  or bus messages, and never push it. Record only the independently verifiable
  fact (a symbol name, a layout decision) and mark it as "GDK-confirmed" without
  quoting the source. Public documentation and the AMD machine-readable ISA
  remain the only citable sources.
  NDA material must never be a dependency, a deliverable, or an acceptance
  criterion of any project here, and in particular not of `rdna2-spirv`. That
  project must stay reproducible from public sources (AMD machine-readable ISA,
  LLVM, SPIR-V specifications) with nothing else installed.
- 2026-11-22: `rdna2-spirv/` is a **git submodule** — a separate repository
  (`lynxnathan/rdna2-spirv`), not part of this history. It keeps its own
  `plan.md` and `investigation.md`. Never journal its work in this
  repository's `investigation.md`, never list it in the root `plan.md`, and
  never copy its files into this tree. Commit it there first, then bump the
  submodule pointer here.
- 2026-11-22: Publication model until outside contributions arrive: remote
  `main` is a **single squashed commit** carrying the whole tree, refreshed by
  force from the local `publication` branch. Local `main` keeps the full
  history. When the project starts receiving external notice or contributions,
  switch to the usual procedure (normal commits, branches, review) and stop
  rewriting remote history. Licence: MIT.
- Future standing instructions from the operator are appended to this section.

## Tooling

- Save every analysis script that works in `tools/` before reporting its result.
  Do not leave a successful one-off script only in shell history or an inline
  heredoc.
- Make tools reproducible from the repository root, for example
  `python3 tools/root_names.py`.
- Prefer standalone Python tools with `argparse` and clear tabular output. Share
  helpers only when it reduces duplication.
- Update the relevant command block in a new journal entry or in the tool table
  in `plan.md` when adding a tool.

## Collaboration protocol

> 2026-11-21: the `script` and `data` worktrees were archived and removed.
> Only `main` remains. These rules are retained as the protocol if a second
> workstream is ever recreated; they are not active worktrees today.

### Roles and cost split

- **Script/integrator does the grunt work:** bulk scans, extraction,
  normalization, tooling, candidate generation, docs, and integration.
- **Data/high-cost model provides the overall picture:** architecture, format
  interpretation, cross-archive hypotheses, priority calls, and validation. It
  should not run long scans.
- If the high-cost model needs a scan, it writes a one-paragraph request; the
  script side runs it and returns a compact table.
- Batch one request/answer per cycle. Skip idle pings. In dual-session standby,
  `bus.py wait --as <name> --since <id>` blocks on direct inotify delivery and
  stays alive across harness yields.
- One driver/owner per active request. `claim`/`release` only for actual
  overlap. If an owner is blocked on the other side, report the dependency.

### Worktrees

| Worktree | Branch | Owner | Scope |
| --- | --- | --- | --- |
| `REPO_ROOT` | `main` | integrator | Integration, shared docs, merge target |
| `SCRIPT_WORKTREE` | `investigate/script-graph` | script workstream | `script.rpf` object graph, RPF9 metadata, Front A/cipher |
| `DATA_WORKTREE` | `investigate/data-rpf` | data workstream | `data.rpf`, localization, model/bone/layout semantics |

- `main` owns `plan.md`, `AGENTS.md`, `investigation.md`, and merges.
- There is a single `investigation.md`. The old per-workstream journals
  (`investigation-script.md`, `investigation-data.md`) are gone; their evidence
  is folded into the main journal. Owners keep their own `tools/` and `handoff/`
  prefixes.
- The samples (`*.rpf`) and `output/` are local and untracked. Never commit them.
- Do not edit another workstream's files. Add a new file instead of changing a
  shared tool in place.

### Merge rules

- Both worktrees merge `main` before starting work and before committing.
- No direct commits to `main` from a worktree.
- Workstream commits use `script:` or `data:` prefixes; docs use `docs:`.
- On a conflict in `plan.md` or `AGENTS.md`, keep `main`'s version and move the
  workstream detail into its own plan/journal.
- `investigation.md` is the one journal, append-only. There are no
  per-workstream journals any more; new evidence is appended at the end.
- Commit early and often; uncommitted work is not shared.

### Handoff contract

Publish handoffs as TSV files under `handoff/`:

- `data-model-bones.tsv` — model name, model hash, bone list, layout
- `data-layouts.tsv` — layout hash, layout name, entry/bone mapping
- `data-names.tsv` — hash, name, kind, source, confidence
- `data-localization.tsv` — key, language, text
- `script-roots.tsv` — root hash, name, class, source
- `script-types.tsv` — type/class ID, role, evidence

Each workstream also keeps `handoff/<stream>-status.md` with four sections:
**Done**, **Artifacts**, **Needs**, and **Next**.

## Bus

- The visible cross-workstream channel is
  `BUS_DIR/messages.jsonl`, driven by
  `tools/bus.py`.
- At the start of a turn, run
  `python3 tools/bus.py digest --as script` (or `--as data`) and answer open
  requests. Use `read --as <name>` for full bodies and `send` for replies.
  Useful commands: `python3 tools/bus.py log`; `read --as data`;
  `send --from data --to script --kind answer --body "..."`.
- Check the bus again before ending a turn or posting a final report. In
  dual-session mode, report completed work on the bus and continue waiting.
- Do not use hidden RPC. The user can read, tail, or inject messages as
  `operator` at any time.
- Batch one request or answer per cycle. Answers should point at artifact paths
  and include a three-line summary.
- For standby use `bus.py wait --as <name> --since <id>` or
  `tools/bus_loop.sh <name> <id>`; the latter polls forever with a maximum
  1 s wait and prints only delivered messages. A bare `wait` exits 0 on
  delivery and 2 on its 1 s default deadline.
- The subscriber reads once after registration, then on a messages.jsonl
  event or IN_Q_OVERFLOW. Cursor writes do not trigger a read. Inotify
  failure is reported explicitly.
- `digest` closes a request only on a terminal `answer` or `handoff` (and
  legacy `result`). A linked `note`, `working`, or `NO_ACK` reply leaves the
  request open.
- Use English for all bus messages.

### Dual-session setup

- Confirm the two active sessions, their worktrees, and which one is `script`
  and which one is `data`. Check `git worktree list` for the actual paths.
  Use English for every bus message.
- Start with one digest per turn. Use `read --since <id-before-request>` when
  the digest has already marked a message seen. Attach replies with
  `send --reply-to <id>`. Send the result or decision directly on the bus
  with artifact paths so the operator does not have to relay it.
- Throughout a dual-session run, both sessions keep their turns open. The
  inotify subscriber blocks until an event. A harness yield leaves the
  subscriber alive without rereading the log or sending an idle ping.
- Negotiate acknowledgment, progress, and result timing per message when it
  matters. The sender can request when they need an acknowledgment or update.
  The receiver can accept or counter with an ETA for that request. For quick
  work, the result is the acknowledgment. For longer work, send one compact
  `working` update after starting, with an ETA if known. Send another update
  only when the agreed timing changes, work is blocked, or the sender asked for
  it. Do not acknowledge acknowledgments. Use local artifact links for bulk
  evidence.
- For each active handoff, the lead tracks the acknowledgment deadline from
  dispatch, up to five minutes. A result or `working` update counts as an
  acknowledgment. If none arrives by the deadline, record one `NO_ACK` note
  with the request ID and keep the request open for a later reply. The worker
  does not wait five minutes to start or to report that work has begun.
- One driver/owner per active request. Use `claim` and `release` only if
  overlapping work actually occurs. If an open request's owner is blocked on
  the other side, report that dependency instead of silently waiting.
- The JSONL bus stores messages. It cannot start a new turn in an idle
  session. Confirm that both turns are active before relying on automatic
  handoffs. If a session is unavailable, tell the operator which side could not be
  reached.

## Documentation

- `plan.md` is only the live check/todo list. Open checks only; no findings and
  no completed-work log.
- `investigation.md` carries the research record. It is an append-only journal;
  add new evidence as dated entries at the end. Do not rewrite or reorganize
  existing entries, and do not keep research state in `plan.md`.
- `format.md` documents the CLI report formats.

## Evidence

- Append results to `investigation.md` as journal entries, separating verified
  observations from hypotheses and review suggestions. Put status changes and
  next actions in `plan.md`.
- Ranges are start-inclusive and end-exclusive. State whether an offset is
  archive-relative or pack-relative.
- Keep samples, extracted output, and generated artifacts local. Do not upload
  them.
- A confirmed archive entry requires a decoded record that independently
  predicts a verified payload byte range.

## Current leads

- Object tree: JOAAT names, 306 of 483 roots named, 136 struct groups over 81
  sizes.
- Schema: LSCH/PSIN expose `x`, `y`, `z`, `datatype`, `name`, `flags`, `item`.
- Front A milestone testbed: `story000_bvh4.rpf`, which has four exact XML
  ranges.
- The 331,728-byte script blob is parked until PC launch; it does not block the
  forest or `common.rpf` work.
