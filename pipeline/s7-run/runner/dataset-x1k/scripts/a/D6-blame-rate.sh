#!/usr/bin/env bash
# D6-blame-rate.sh, machine A (read-only, through scripts/a/ssm-a.sh): per row in step 7, the .blame files
# finished per hour since the start of the newest attempt (by .blame mtime), with the source bytes of
# these files, and the size quantiles of the files done in the last hour and of the files left.
# For a row past step 7: the timestamps of the step headings of the newest attempt.
# Use: I=<id> TAILN=120 bash scripts/a/ssm-a.sh scripts/a/D6-blame-rate.sh 900
set -uo pipefail
L=/data/x1k-long
S=$(date -d "$(awk '{print $2}' $L/started)" +%s)
echo "== $(date -u +%FT%TZ); attempt start $(date -u -d @$S +%FT%TZ)"
for p in $(cat $L/run.list); do R=$(readlink -f $L/$p)
  systemctl is-active -q x1k-long@$p || continue
  O=$R/out/$p; W=$O/$p-cregit; PL=$O/pipeline.log
  echo "--- $p"
  a=$(grep -a -n -E 'Step 7 —' $PL | tail -1 | cut -d: -f1)
  if grep -a -q -E 'Step 10 —' <(tail -n +${a:-1} $PL); then
    tail -n +${a:-1} $PL | grep -a -E 'Step [0-9]+ —|completed in|^\[20[0-9-]+ [0-9:]+\]' | grep -a -v -- '->' | tail -12 | cut -c1-200
    ls -la --time-style=+%FT%T $O | grep -a -E 'parquet|duckdb|sync_' | awk '{print "  ", $5, $6, $7}'
    continue
  fi
  sudo -u ec2-user git -C "$W" ls-files | python3 -c '
import os, re, sys, time
w, b, s0 = sys.argv[1], sys.argv[2], int(sys.argv[3])
rx = re.compile(r"(?i)\.(c|c\+\+|cc|cp|cpp|cxx|h|h\+\+|hh|hpp|hxx|java|rs|tcc)$")
now = time.time(); hours = {}; last = []; left = []
for line in sys.stdin:
    f = line.rstrip("\n")
    if not rx.search(f):
        continue
    try:
        s = os.path.getsize(os.path.join(w, f))
    except OSError:
        continue
    try:
        m = os.path.getmtime(os.path.join(b, f + ".blame"))
    except OSError:
        left.append(s); continue
    if m >= s0:
        h = int((m - s0) // 3600); c = hours.setdefault(h, [0, 0]); c[0] += 1; c[1] += s
        if now - m < 3600:
            last.append(s)
def q(v):
    v = sorted(v)
    return "n=%d p50=%.1fKB p90=%.1fKB max=%.1fKB" % (len(v), v[len(v)//2]/1e3, v[int(len(v)*0.9)]/1e3, v[-1]/1e3) if v else "n=0"
print("  per hour since attempt start (files, MB):", " ".join("h%d:%d/%.1f" % (h, c[0], c[1]/1e6) for h, c in sorted(hours.items())))
print("  last 60 min:", q(last), "; left:", q(left), "sum %.1f MB" % (sum(left)/1e6))
' "$W" "$O/blame" "$S"
done
exit 0
