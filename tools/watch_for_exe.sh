#!/usr/bin/env bash
# Watch the drop folders and audit anything that arrives, without running it.
#
#   setsid nohup tools/watch_for_exe.sh >/tmp/watch-exe.log 2>&1 &
#
# Uses inotify (inotifywait). On a new .exe/.zip/.7z it writes a hash, runs
# tools/pe_audit.py (PE) or lists the archive (zip/7z), appends to
# cache/exe-audit/reports.log and raises a desktop notification.
set -uo pipefail
cd "$(dirname "$0")/.."
out=cache/exe-audit
mkdir -p "$out"
watched=("$HOME/Downloads" "$HOME/gta6-exe-audit")
for d in "${watched[@]}"; do mkdir -p "$d"; done

echo "$(date -Is) watching ${watched[*]}" >> "$out/reports.log"
inotifywait -m -q -e close_write -e moved_to --format '%w%f' "${watched[@]}" |
while read -r path; do
    case "${path,,}" in
        *.exe) kind=pe ;;
        *.zip|*.7z|*.rar) kind=archive ;;
        *.part|*.tmp|*.crdownload) continue ;;
        *) continue ;;
    esac
    echo "$(date -Is) $kind $path" >> "$out/reports.log"
    {
        echo "== $(date -Is) $path"
        sha256sum "$path" 2>/dev/null
        if [ "$kind" = pe ]; then
            python3 tools/pe_audit.py "$path"
        else
            unzip -l "$path" 2>/dev/null | head -20 || 7z l "$path" 2>/dev/null | head -20
        fi
    } >> "$out/reports.log" 2>&1
    notify-send -a "gta6 exe audit" "new ${kind}: $(basename "$path")" \
        "$(tail -3 "$out/reports.log" | tr '\n' ' ')" 2>/dev/null || true
done
