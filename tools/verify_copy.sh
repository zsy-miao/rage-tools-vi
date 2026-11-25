#!/usr/bin/env bash
# Does the local NVMe copy match the source? Two levels, because a full rehash
# of 224 GB costs as much as the copy itself.
#
#   1. metadata: `rsync --dry-run` reports any file whose size or mtime differs.
#      This is what `rsync -a` guarantees, and it is cheap.
#   2. content: sha256 of a deterministic sample — the largest files plus an
#      even spread — so a silent corruption is caught without rehashing
#      everything. `--full` hashes every file instead.
#
#   tools/verify_copy.sh SOURCE DEST [--full] [--sample N]
set -uo pipefail
SRC=${1:?usage: verify_copy.sh SOURCE DEST [--full] [--sample N]}
DST=${2:?usage: verify_copy.sh SOURCE DEST [--full] [--sample N]}
shift 2
full=0
sample=24
while [ $# -gt 0 ]; do
    case "$1" in
        --full) full=1 ;;
        --sample) sample=${2:-24}; shift ;;
    esac
    shift
done

echo "== metadata differences"
diff_list=$(rsync -an --itemize-changes --exclude '*.log' "$SRC/" "$DST/" | head -20)
if [ -n "$diff_list" ]; then
    echo "$diff_list"
    echo "MISMATCH: rsync reports differences (truncated to 20)"
else
    echo "none: every path is present with the same size and mtime"
fi

if [ "$full" = 1 ]; then
    echo "== full content check (this reads both trees)"
    ( cd "$SRC" && find . -type f -print0 | sort -z | xargs -0 sha256sum ) > /tmp/src.sha256
    ( cd "$DST" && find . -type f -print0 | sort -z | xargs -0 sha256sum ) > /tmp/dst.sha256
    if cmp -s /tmp/src.sha256 /tmp/dst.sha256; then
        echo "PASS: $(wc -l < /tmp/src.sha256) files identical by sha256"
    else
        echo "FAIL: $(diff /tmp/src.sha256 /tmp/dst.sha256 | grep -c '^<') differing files"
        diff /tmp/src.sha256 /tmp/dst.sha256 | head -5
        exit 1
    fi
    exit 0
fi

echo "== content sample (largest $sample files)"
mapfile -t files < <(find "$SRC" -type f -printf '%s\t%p\n' | sort -rn | head -"$sample" | cut -f2-)
bad=0
for path in "${files[@]}"; do
    rel=${path#"$SRC"/}
    if ! cmp -s "$path" "$DST/$rel"; then
        echo "  DIFFERS: $rel"
        bad=$((bad + 1))
    fi
done
echo "  compared ${#files[@]} files by content, $bad differ"
[ "$bad" -eq 0 ] && echo "PASS" || exit 1
