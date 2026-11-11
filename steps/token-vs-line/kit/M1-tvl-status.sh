#!/usr/bin/env bash
# M1-tvl-status.sh (the token-vs-line machine, root, through ssm-tvl.sh; read only): the status files, the unit,
# a scheduled shutdown, disk, memory, load, the progress (project states, files blamed, running projects, the
# time to the run cap), the failures so far and the last log lines.
set -uo pipefail
IID=${TVL_IID:-$(cat /sys/devices/virtual/dmi/id/board_asset_tag)}
case "||" in
  *"|$IID|"*) echo "ABORT: $IID is not the token-vs-line machine"; exit 1 ;; esac
X=${TVL_X:-/data/tvl}; PY=${TVL_PY:-$X/venv/bin/python}
echo "== $(date -u +%FT%TZ) run ${TVL_RUN:-?}"
for f in $X/status/run.*; do [ -f $f ] && echo "$(basename $f): $(cut -c1-300 $f)"; done
echo "tvl-run: $(systemctl is-active tvl-run 2>/dev/null)"; [ -f /run/systemd/shutdown/scheduled ] && echo "a shutdown is scheduled: $(grep -o 'USEC=[0-9]*' /run/systemd/shutdown/scheduled | cut -c6- | awk '{print strftime("%FT%TZ", $1/1000000, 1)}')"
[ -e /run/tvl-hold ] && echo "hold: set"
df -h /data1 2>/dev/null | tail -1; free -g | awk '/Mem:/{print "memory: total "$2" GiB, available "$7" GiB"}'; uptime
echo "git jobs now: $(pgrep -c -x git || true)"
[ -f $X/log/progress.json ] && $PY -I -B - $X/log/progress.json <<'P'
import json, sys
p = json.load(open(sys.argv[1]))
print(f"progress {p['utc']}: elapsed {p['elapsed_h']:.2f} h of cap {p['cap_h']} h (blames stop {p['blame_stop_utc']}); "
      f"cut {p['cut']}; final {p['final']}")
print("states:", ", ".join(f"{k} {v}" for k, v in sorted(p["counts"].items())))
print(f"files blamed {p['files_done']} of {p['files_known']} known; failures {p['failures']}; load {p['load1']}; "
      f"disk free {p['disk_free_gb']} GB")
for r in p["running"][:12]:
    print(f"  {r['project'][:50]}: {r['files_done']}/{r['files']} files")
for a in p["alerts"]:
    print("  alert:", a[:200])
P
[ -f $X/log/run.log ] && { echo "-- failures"; grep -E "FAILED|HOLD|ERROR|RUN CAP" $X/log/run.log | tail -8 | cut -c1-240; echo "-- run.log"; tail -${TAILN_LOG:-8} $X/log/run.log | cut -c1-240; }
true
