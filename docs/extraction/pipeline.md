# Full output pipeline

`tools/pipeline.py` is the reproducible entry point for the rebuilt corpus.
It wraps the streaming indexer, bulk extractor, verifier, audio codecs, and
extraction pilot behind one safe command.

```sh
python3 tools/pipeline.py --source SOURCE_ROOT --output output all --resume
```

## Subcommands

| Command | Action |
| --- | --- |
| `index` | bounded zlib index for all eight large archives |
| `extract` | bulk extract + verify six selected archives |
| `audio` | rebuild AWC, XMA2, Opus, and ACE1 output |
| `pilot` | build the static eight-root browser |
| `verify` | re-verify every extracted manifest |
| `all` | index → extract → audio → pilot → verify |

## Safety

- Existing non-empty output requires `--resume` or `--force`.
- `--force` deletes only the target output area; `--resume` continues.
- `--dry-run` prints every command without touching the output tree.
- Every run appends a command/return-code record to
  `output/pipeline-runs.jsonl`.
- The source archive set is fixed in the script; missing archives abort before
  any work.

The legacy `tools/export_all.sh` remains as a shell wrapper for the same
large-archive set.
