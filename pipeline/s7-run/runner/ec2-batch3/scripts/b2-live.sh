set -euo pipefail
cat > /usr/local/bin/census-steps <<'EOF_census-steps'
#!/usr/bin/env python3
"""census-steps CTP_DIR MANIFEST [--highlight REGEX]: the cregit step of every running project.

Read-only: it reads CTP_DIR/ledger.jsonl and CTP_DIR/state/<name>/logs/*.log and prints a table.
A project is running when its last ledger row in the newest census run is not the final
"project" row. For a project in the ctp "pipeline" phase the step is the last "Step N — name"
header in its newest pipeline log. The runner prints no time on a header, so the step start is
computed: the pipeline start (the ledger "pipeline started" row of that attempt) plus the
"completed in Ns" of every earlier step in the same log. That is exact to a second or two.
Projects whose name matches --highlight (default LineageOS) are always listed first, with
their state even when they are not running (queued, done, failed).
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

HEADER = re.compile(r"^\s*Step (\d+) — (.+?)\s*$")
DONE = re.compile(r"✓ completed in (\d+)s")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def parse_utc(text):
    try:
        t = dt.datetime.fromisoformat(text)
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def fmt_age(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


def manifest_names(path):
    names = []
    for line in Path(path).read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            names.append(line.split("\t")[0])
    return names


def ledger_rows(ctp):
    rows = []
    try:
        with (ctp / "ledger.jsonl").open() as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return rows


def newest_log(state, name, phase):
    logs = sorted((state / name / "logs").glob(f"{phase}-2*.log"))
    return logs[-1] if logs else None


def last_line(path):
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 8192))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return ""
    lines = [ANSI.sub("", l).strip() for l in tail.replace("\r", "\n").splitlines()]
    lines = [l for l in lines if l and not set(l) <= set("═█")]
    return lines[-1][:150] if lines else ""


def pipeline_step(log, base):
    """(step, name, start) of the last header in log; start from base plus completed steps."""
    step = name = None
    elapsed = 0
    start = None
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None, None
    for line in text.splitlines():
        m = HEADER.match(line)
        if m:
            step, name = int(m.group(1)), m.group(2)
            start = base + dt.timedelta(seconds=elapsed) if base else None
            continue
        d = DONE.search(line)
        if d:
            elapsed += int(d.group(1))
    return step, name, start


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ctp")
    ap.add_argument("manifest")
    ap.add_argument("--highlight", default="LineageOS")
    args = ap.parse_args()
    ctp = Path(args.ctp)
    state = ctp / "state"
    now = dt.datetime.now(dt.timezone.utc)
    names = manifest_names(args.manifest)
    rows = ledger_rows(ctp)
    runs = [r for r in rows if r.get("step") == "run-start" and r.get("command", "census") == "census"]
    run_id = runs[-1].get("run_id") if runs else (rows[-1].get("run_id") if rows else None)
    cur = [r for r in rows if r.get("run_id") == run_id and r.get("project")]
    last, pipe_start, finals, started = {}, {}, {}, set()
    for r in cur:
        p = r["project"]
        last[p] = r
        started.add(p)
        if r.get("step") == "pipeline" and r.get("status") == "started":
            pipe_start[p] = parse_utc(r.get("start_utc"))
        if r.get("step") == "project":
            finals[p] = r.get("state")
    # Final state over all runs, for projects that this run skipped (no ledger row).
    ever = {}
    for r in rows:
        if r.get("step") == "project" and r.get("project"):
            ever[r["project"]] = r.get("state")
    running = [n for n in names if n in last and last[n].get("step") != "project"]
    pending = [n for n in names if n not in started and ever.get(n) not in ("done", "done-dirty", "skipped")]
    print(f"as of {now:%Y-%m-%dT%H:%M:%SZ}  run {run_id}  running {len(running)}  "
          f"not started {len(pending)}  manifest {len(names)}")
    print("step start = pipeline start + the 'completed in' of the earlier steps (computed)")
    print()
    fmt = "{:<40} {:<9} {:<34} {:<20} {:>8}  {}"
    print(fmt.format("PROJECT", "PHASE", "CREGIT STEP", "STEP START (UTC)", "ELAPSED", "LAST LOG LINE (age)"))
    hl = re.compile(args.highlight) if args.highlight else None
    order = [n for n in names if hl and hl.search(n)] + [n for n in running if not (hl and hl.search(n))]
    for n in order:
        if n not in running:
            st = finals.get(n) or ever.get(n) or ("queued" if n in pending else "?")
            print(fmt.format(n[:40], st, "-", "-", "-", "(not running)"))
            continue
        r = last[n]
        phase = r.get("step", "?")
        step_txt, start_txt, el_txt = "-", "-", "-"
        log = newest_log(state, n, "pipeline") if phase == "pipeline" else newest_log(state, n, phase)
        if phase == "pipeline" and log:
            step, sname, start = pipeline_step(log, pipe_start.get(n))
            if step:
                step_txt = f"{step} {sname}"[:34]
                if start:
                    start_txt = f"{start:%Y-%m-%d %H:%M:%S}"
                    el_txt = fmt_age((now - start).total_seconds())
        else:
            st = parse_utc(r.get("start_utc"))
            if st:
                start_txt = f"{st:%Y-%m-%d %H:%M:%S}"
                el_txt = fmt_age((now - st).total_seconds())
        tail = ""
        if log:
            age = now.timestamp() - log.stat().st_mtime
            tail = f"{last_line(log)} ({fmt_age(age)} ago)"
        print(fmt.format(n[:40], phase, step_txt, start_txt, el_txt, tail))
    return 0


if __name__ == "__main__":
    sys.exit(main())
EOF_census-steps
chmod 755 /usr/local/bin/census-steps
cat > /usr/local/bin/census-batch2-live <<'EOF_census-batch2-live'
#!/usr/bin/env bash
# Every 10 min (census-batch2-live.timer): status of the census to s3://BUCKET/batch2/live/.
# 2026-10-09 03:15: adds steps.txt (census-steps: the cregit step of each running project,
# its computed start, elapsed time and the last log line; LineageOS always listed first),
# and appends the same table to progress.txt.
set -uo pipefail
D=s3://${RUNNER_BUCKET}/batch2/live
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export CTP_CONFIG=/home/ec2-user/census-batch2.cfg
M=/home/ec2-user/batch2-input/manifest.batch2.tsv
/usr/local/bin/census-steps /home/ec2-user/ctp "$M" --highlight LineageOS > "$T/steps.txt" 2>&1
{ echo "as of $(date -u +%FT%TZ)  census-batch2: $(systemctl is-active census-batch2.service) ($(systemctl show census-batch2.service -p Result --value))"
  echo "uptime: $(uptime)"
  echo "MemAvailable: $(awk '/MemAvailable/{printf "%.1f GiB", $2/1048576}' /proc/meminfo)   /data free: $(df -BG --output=avail /data | tail -1 | tr -d ' ')"
  echo
  (cd /home/ec2-user/ctp && .venv/bin/python ctp.py progress --manifest "$M" --last 10 2>&1)
  echo; echo "=== steps"; cat "$T/steps.txt"
} > "$T/progress.txt"
tail -n 300 /data/logs/batch2.log > "$T/batch2.log.tail" 2>/dev/null || true
{ date -u +%FT%TZ; uptime; cat /proc/meminfo; df -h /data /; } > "$T/system.txt"
[ -f /home/ec2-user/ctp/ledger.jsonl ] && cp /home/ec2-user/ctp/ledger.jsonl "$T/ledger.jsonl"
aws s3 cp "$T/" "$D/" --recursive --only-show-errors
EOF_census-batch2-live
chmod 755 /usr/local/bin/census-batch2-live
set -uo pipefail
B=/usr/local/bin
[ -e $B/census-batch2-live.orig-20261009 ] || cp -p $B/census-batch2-live $B/census-batch2-live.orig-20261009
bash -n $B/census-batch2-live && python3 -m py_compile $B/census-steps && echo syntax ok
rm -rf $B/__pycache__
sudo -u ec2-user $B/census-batch2-live; echo "live rc=$?"
aws s3 cp s3://${RUNNER_BUCKET}/batch2/live/steps.txt - | cut -c1-200
systemctl is-active census-batch2.service; systemctl list-timers census-batch2-live.timer --no-pager | sed -n 2p
