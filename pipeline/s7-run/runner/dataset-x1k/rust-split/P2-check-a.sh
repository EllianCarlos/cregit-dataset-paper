#!/usr/bin/env bash
# P2-check-a.sh, machine A (read-only; root through scripts/a/ssm-a.sh): the state of the split as
# machine A sees it. The newest rs-pull block, the timer, ALERT/HOLD, the batches applied per part,
# the files pulled per hour (last 6 h), A's newest started index and the head and tail of the
# split, the status line of each part (from the last pull), the .blame files of the row per hour
# (A's own and the pulled ones together: the pulled files keep the mtime of the extra), the files
# left (mask files without a .blame, as D5) and an ETA = left / (files per hour of the last 2 h).
# Output: counts only; each at sign is dropped.
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
[ "$IID" = ${RUNNER_EC2_X1K_LONG_A4} ] || { echo "ABORT: $IID is not machine A"; exit 1; }
P=awslabs__aws-sdk-rust
S=/data/x1k-long/rust-split
main() {
T=$(readlink -f /data/x1k-long/$P); W=$T/out/$P/$P-cregit; BL=$T/out/$P/blame; now=$(date +%s)
echo "== $(date -u +%FT%TZ) P2 on $IID; row unit $(systemctl is-active x1k-long@$P); newest step heading: $(grep -a -E '^  Step [0-9]+ ' "$T/out/$P/pipeline.log" | tail -1 | cut -c1-60)"
echo "rs-pull.timer $(systemctl is-active rs-pull.timer); ALERT $([ -e $S/ALERT ] && echo PRESENT || echo absent); HOLD $([ -e $S/HOLD ] && echo PRESENT || echo absent); restarts by rs-pull: $(wc -l < $S/state/restarts.log 2>/dev/null || echo 0)"
n=$(grep -n '^== .* rs-pull on' $S/state/pull.log 2>/dev/null | tail -1 | cut -d: -f1)
[ -n "$n" ] && tail -n +"$n" $S/state/pull.log | grep -v '^  pull: part' | head -20
echo "--- split (E1): $(grep -e '^left' -e '^head' $S/e1/parts/split.txt | tr '\n' ';')"
echo "--- applied batches per part (status ok / bad), files linked, exists"
awk -F'\t' '{b[$1]++; if ($4 != "ok") bad[$1]++; l[$1] += $5; e[$1] += $6} END {for (k in b) printf "  part %s: %d batches (bad %d), linked %d, exists %d\n", k, b[k], bad[k], l[k], e[k]}' $S/state/pull/applied.tsv 2>/dev/null | sort
echo "--- files linked per hour (last 6 h)"
awk -v now="$now" '{h = int((now - $1) / 3600); if (h < 6) c[h]++} END {for (h = 5; h >= 0; h--) printf "  %d-%d h ago: %d\n", h + 1, h, c[h]}' $S/state/pull/linked.tsv 2>/dev/null
echo "--- parts (status.txt of the last pull)"
for f in $S/state/status/*.txt; do [ -f "$f" ] || continue
  echo "  $(basename "$f" .txt): $(sed -n '1p;2p;4p;5p;6p' "$f" | tr '\n' '|' | cut -c1-400)"; done
echo "--- .blame of the row by mtime (A and pulled), per hour (last 6 h)"
find "$BL" -name '*.blame' -newermt '-6 hours' -printf '%T@\n' 2>/dev/null | awk -v now="$now" '{h = int((now - $1) / 3600); c[h]++} END {for (h = 5; h >= 0; h--) printf "  %d-%d h ago: %d\n", h + 1, h, c[h]}'
mask=$(head -1 $S/e1/mask.txt)
left=$(sudo -u ec2-user git -C "$W" ls-files | python3 -I -c '
import os, re, sys
w, b, mask = sys.argv[1], sys.argv[2], sys.argv[3]
rx = re.compile(mask) if mask else None
n = 0
for line in sys.stdin:
    f = line.rstrip("\n")
    if (rx is None or rx.search(f)) and os.path.isfile(os.path.join(w, f)) and not os.path.exists(os.path.join(b, f + ".blame")):
        n += 1
print(n)' "$W" "$BL" "$mask")
r2=$(find "$BL" -name '*.blame' -newermt '-2 hours' | wc -l)
echo "files left: $left; done in the last 2 h: $r2; ETA: $(awk -v l="$left" -v r="$r2" 'BEGIN {if (r > 0) printf "%.1f h at the rate of the last 2 h", l / (r / 2); else print "no rate yet"}')"
uptime
}
main 2>&1 | sed -u 's/@//g'
