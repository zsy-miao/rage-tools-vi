#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${DOCS_VENV:-$ROOT/.venv-docs}"
if [ ! -x "$VENV/bin/mkdocs" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r "$ROOT/requirements-docs.txt"
fi
cd "$ROOT"
case "${1:-serve}" in
  build) exec "$VENV/bin/mkdocs" build --clean ;;
  serve) exec "$VENV/bin/mkdocs" serve ;;
  *) exec "$VENV/bin/mkdocs" "$@" ;;
esac
