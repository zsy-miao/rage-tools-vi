#!/usr/bin/env bash
# One command that answers "is this repository still healthy?".
#
#   tools/check.sh          # data tests, index invariants, submodule tests, docs
#   tools/check.sh --fast   # skip the docs build and the submodule suite
#
# Every check is something a contributor can run from a fresh clone; anything
# that needs the archives is skipped with a message rather than failed.
set -uo pipefail
cd "$(dirname "$0")/.."
# Prefer `uv run` when a managed environment is present, so tools get their
# declared dependencies (numpy for the XMA2 wrapper) without a global install.
PY=python3
if command -v uv >/dev/null && [ -f pyproject.toml ] && uv run python -c "" >/dev/null 2>&1; then
    PY="uv run python"
fi

fast=0
[ "${1:-}" = "--fast" ] && fast=1
fail=0
note() { printf '%-26s %s\n' "$1" "$2"; }

# Every tool must at least parse: a syntax error in an unexercised script is a
# silent hole in "you can run this from a fresh clone".
if $PY -m compileall -q tools >/tmp/check-compile.log 2>&1; then
    note "tool syntax" "PASS ($(ls tools/*.py | wc -l) modules)"
else
    note "tool syntax" "FAIL"; tail -5 /tmp/check-compile.log | sed 's/^/    /'; fail=1
fi

if $PY tests/test_analysis_tools.py >/tmp/check-tools.log 2>&1; then
    note "analysis tools" "PASS ($(grep -c '  ok' /tmp/check-tools.log) checks)"
else
    note "analysis tools" "FAIL"; tail -5 /tmp/check-tools.log | sed 's/^/    /'; fail=1
fi

# A symlink named `output` slipped into the published tree once, because
# `.gitignore`'s `/output/` matches a directory but not a symlink.
if git ls-files -s | awk '$1 == 120000 {print $4}' | grep -q .; then
    note "tracked symlinks" "FAIL: $(git ls-files -s | awk '$1 == 120000 {print $4}' | tr '\n' ' ')"
    fail=1
else
    note "tracked symlinks" "PASS (none)"
fi

if $PY tools/tool_index.py --check >/tmp/check-toolsindex.log 2>&1; then
    note "tool index" "PASS ($(head -1 /tmp/check-toolsindex.log | sed 's/.*current (//;s/ tools)//'))"
else
    note "tool index" "FAIL"; tail -3 /tmp/check-toolsindex.log | sed 's/^/    /'; fail=1
fi

if $PY tools/handoff_manifest.py --check >/tmp/check-handoff.log 2>&1; then
    note "handoff provenance" "PASS ($(sed 's/.*listed, //' /tmp/check-handoff.log))"
else
    note "handoff provenance" "FAIL"; tail -5 /tmp/check-handoff.log | sed 's/^/    /'; fail=1
fi

if $PY tools/claims_check.py >/tmp/check-claims.log 2>&1; then
    note "published counts" "PASS ($(grep -c . /tmp/check-claims.log) line)"
else
    note "published counts" "FAIL"; sed 's/^/    /' /tmp/check-claims.log | head -6; fail=1
fi

if compgen -G "output/index/*.tsv" >/dev/null && [ -n "$(ls *.rpf 2>/dev/null)" ]; then
    if $PY tools/pack_extent_check.py --all >/tmp/check-extents.log 2>&1; then
        note "pack extents" "PASS ($(grep -c 'packs,' /tmp/check-extents.log) archives)"
    else
        note "pack extents" "FAIL"; grep -E "escaped|crossing|covered" /tmp/check-extents.log | head -5 | sed 's/^/    /'; fail=1
    fi
else
    note "pack extents" "skipped (no archives or indexes)"
fi

if compgen -G "output/index/*.tsv" >/dev/null; then
    if $PY tools/index_coverage.py >/tmp/check-coverage.log 2>&1; then
        note "index coverage" "PASS ($(grep -c '%' /tmp/check-coverage.log) rows)"
    else
        note "index coverage" "FAIL"; tail -3 /tmp/check-coverage.log | sed 's/^/    /'; fail=1
    fi
fi

if compgen -G "output/index/*.tsv" >/dev/null; then
    if $PY tools/chain_start_verify.py output/index/*.tsv >/tmp/check-index.log 2>&1; then
        note "index invariants" "PASS ($(grep -c '\.tsv' /tmp/check-index.log) indexes)"
    else
        note "index invariants" "FAIL"; tail -3 /tmp/check-index.log | sed 's/^/    /'; fail=1
    fi
else
    note "index invariants" "skipped (no indexes)"
fi

if [ "$fast" -eq 0 ] && [ -x rdna2-spirv/tests/run_all.sh ]; then
    if (cd rdna2-spirv && bash tests/run_all.sh >/tmp/check-spirv.log 2>&1); then
        note "rdna2-spirv suite" "PASS ($(grep -c PASS /tmp/check-spirv.log) lines)"
    else
        note "rdna2-spirv suite" "FAIL"; tail -6 /tmp/check-spirv.log | sed 's/^/    /'; fail=1
    fi
fi

if [ "$fast" -eq 0 ] && [ -x tools/docs.sh ]; then
    if tools/docs.sh build >/tmp/check-docs.log 2>&1; then
        note "docs build" "PASS"
    else
        note "docs build" "FAIL"; tail -5 /tmp/check-docs.log | sed 's/^/    /'; fail=1
    fi
fi

echo
[ "$fail" -eq 0 ] && echo "PASS" || echo "FAIL"
exit "$fail"
