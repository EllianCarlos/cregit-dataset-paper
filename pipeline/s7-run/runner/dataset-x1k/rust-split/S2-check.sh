#!/usr/bin/env bash
# S2-check.sh, an extra machine (read-only; root through rust-split/ssm-rs.sh): the units, the phase,
# the gate result, the driver progress, .blame files per hour (last 6 h by mtime), the batches sent,
# PLAIN-BLAME and error counts, the git blame processes, load and memory, and an ETA for this part:
# the files of the part above A's position plus the margin that are neither done nor started,
# divided by the files per hour of the last 2 h. Output: counts only; each at sign is dropped.
set -uo pipefail
main() {
. /etc/rust-split/rs.env
now=$(date +%s)
echo "== $(date -u +%FT%TZ) S2 part $K ($NAME) on $(cat /sys/devices/virtual/dmi/id/board_asset_tag); jobs $JOBS margin $MARGIN"
echo "units: rs-run $(systemctl is-active rs-run), rs-upload $(systemctl is-active rs-upload); phase $(cat /rs/state/phase 2>/dev/null)"
echo "gate: $(cat /rs/state/gate.summary 2>/dev/null || echo 'not run')"
echo "progress: $(cat /rs/state/progress 2>/dev/null || echo none)"
echo "end: $(cat /rs/state/end 2>/dev/null || echo 'not yet'); STOP here: $([ -e /rs/control/STOP ] && echo yes || echo no); a-pos: $(cat /rs/control/apos 2>/dev/null || echo none)"
echo ".blame here per hour:"
find /rs/out/blame -type f -name '*.blame' -newermt '-6 hours' -printf '%T@\n' | awk -v now="$now" '{h = int((now - $1) / 3600); c[h]++} END {for (h = 5; h >= 0; h--) printf "  %d-%d h ago: %d\n", h + 1, h, c[h]}'
echo "batches sent: $(ls /rs/batches/sent 2>/dev/null | wc -l) (newest $(cat /rs/state/seq 2>/dev/null)); names sent $(sort -u /rs/state/sent.list 2>/dev/null | wc -l); pending $(cat /rs/state/pending 2>/dev/null || echo none)"
echo "upload log: $(tail -2 /rs/logs/upload.log 2>/dev/null | tr '\n' '|' | cut -c1-300)"
echo "PLAIN-BLAME $(grep -c '^PLAIN-BLAME ' /rs/logs/blame.log 2>/dev/null); errors $(grep -c '^Error' /rs/logs/blame.log 2>/dev/null); git blame processes $(pgrep -c -f 'git -C .* blame')"
ap=$(cut -d' ' -f1 /rs/control/apos 2>/dev/null); ap=${ap:-0}
low=$(sed -n 's/.*lowest_started \([0-9-]*\).*/\1/p' /rs/state/progress 2>/dev/null)
open=$(awk -F'\t' -v a="$ap" -v m="$MARGIN" -v l="${low:--}" '$1 > a + m && (l == "-" || $1 + 0 < l + 0) {n++} END {print n + 0}' "/rs/in/parts/part-$K.tsv")
r2=$(find /rs/out/blame -type f -name '*.blame' -newermt '-2 hours' | wc -l)
echo "open in this part (index above a-pos + margin, below the lowest started): $open; done in the last 2 h: $r2; ETA $(awk -v o="$open" -v r="$r2" 'BEGIN {if (r > 0) printf "%.1f h", o / (r / 2); else print "no rate yet"}')"
echo "load $(cut -d' ' -f1-3 /proc/loadavg); mem $(free -g | awk '/Mem:/{print $3 " of " $2 " GiB used"}'); disk free $(df -h --output=avail /rs | tail -1)"
}
main 2>&1 | sed -u 's/@//g'
