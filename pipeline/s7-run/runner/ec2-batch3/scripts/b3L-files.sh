set -euo pipefail
cat > /usr/local/bin/census-steps.new <<'EOF_census-steps'
#!/usr/bin/env python3
"""census-steps CTP_DIR MANIFEST [--highlight REGEX]: the cregit step of every running project.

Read-only: it reads CTP_DIR/ledger.jsonl and CTP_DIR/state/<name>/logs/*.log and prints a table.
A project is running when its last ledger row in the newest census run is not the final
"project" row. For a project in the ctp "pipeline" phase the step is the last "Step N — name"
header in its newest pipeline log. The runner prints no time on a header, so the step start is
computed: the pipeline start (the ledger "pipeline started" row of that attempt) plus the
"completed in Ns" of every earlier step in the same log. That is exact to a second or two.
--counts prints only "RUNNING NOT_STARTED". Projects whose name matches --highlight (default LineageOS) are always listed first, with
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
    ap.add_argument("--counts", action="store_true",
                    help='print only "RUNNING NOT_STARTED" for the newest run (for census-batch3L-wait)')
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
    if args.counts:
        print(len(running), len(pending))
        return 0
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
chmod 755 /usr/local/bin/census-steps.new
mv -f /usr/local/bin/census-steps.new /usr/local/bin/census-steps
cat > /usr/local/bin/census-other-done.new <<'EOF_census-other-done'
#!/usr/bin/env bash
# census-other-done SELF: exit 0 when the OTHER census on the batch 2 instance has finalized,
# i.e. its final/DONE is in S3 (a finalize writes DONE only after its upload check passed) and
# its census units are not active. SELF=batch2 -> other is batch3L (waiter + census);
# SELF=batch3L -> other is batch2. Each finalize writes its own DONE before it asks, so the
# second census to finish always sees the first one's DONE and powers off.
# Test overrides: OTHER_DONE_URL (an S3 object), OTHER_UNITS (space-separated; "" = none).
set -uo pipefail
B=s3://${RUNNER_BUCKET}
case ${1:-} in
  batch2)  url=${OTHER_DONE_URL:-$B/batch3L/final/DONE}; units=${OTHER_UNITS-census-batch3L-wait.service census-batch3L.service} ;;
  batch3L) url=${OTHER_DONE_URL:-$B/batch2/final/DONE};  units=${OTHER_UNITS-census-batch2.service} ;;
  *) echo "usage: census-other-done batch2|batch3L" >&2; exit 2 ;;
esac
for u in $units; do
  s=$(systemctl is-active "$u")
  case $s in active|activating|reloading|deactivating) echo "other census not finalized: $u is $s"; exit 1 ;; esac
done
aws s3 ls "$url" >/dev/null 2>&1 || { echo "other census not finalized: $url is missing"; exit 1; }
echo "other census finalized: $url exists, units not active: ${units:-none}"
EOF_census-other-done
chmod 755 /usr/local/bin/census-other-done.new
mv -f /usr/local/bin/census-other-done.new /usr/local/bin/census-other-done
cat > /usr/local/bin/census-batch2-finalize.new <<'EOF_census-batch2-finalize'
#!/usr/bin/env bash
# Runs when census-batch2.service exits (OnSuccess=/OnFailure=). Copies the results to
# s3://BUCKET/batch2/final/, checks every object (key and size) and SHA256SUMS against the
# local files, writes DONE, then powers off (the instance STOPS; the RAID0 is lost).
# No power-off if the check fails, with --dry-run, if the census ran < 1 h, if
# /home/ec2-user/NO_SHUTDOWN exists, or (2026-10-09) if the other census on this instance
# (batch 2 / batch 3L) has not finalized: census-other-done decides; the second one to
# finalize powers off.
# --dry-run: copy to batch2/dryrun/ from CTP/OUT given in the environment, never power off.
# --decide-only: print only the power-off decision (census-other-done), copy nothing.
set -uo pipefail
SELF=batch2
DRY=0; [ "${1:-}" = --dry-run ] && DRY=1
DECIDE=0; [ "${1:-}" = --decide-only ] && DECIDE=1
B=s3://${RUNNER_BUCKET}
CTP=${CTP:-/home/ec2-user/ctp}
OUT=${OUT:-/data/census-2026-10-batch2}
CLOG=${CLOG:-/data/logs/batch2.log}
DEST=${DEST:-$B/batch2/final}; [ $DRY = 1 ] && DEST=${DEST_DRY:-$B/batch2/dryrun}
S_=/data/final-stage; FLOG=/data/logs/finalize.log
exec > >(tee -a "$FLOG") 2>&1
say() { echo "[$(date -u +%FT%TZ)] finalize: $*"; }
fail() { say "FAILED: $*"; echo "finalize failed at $(date -u +%FT%TZ): $*" > /tmp/FINALIZE_FAILED
         aws s3 cp /tmp/FINALIZE_FAILED "$DEST/FINALIZE_FAILED" --only-show-errors; aws s3 cp "$FLOG" "$DEST/finalize.log" --only-show-errors; exit 1; }
if [ $DECIDE = 1 ]; then why=$(/usr/local/bin/census-other-done $SELF 2>&1); rc=$?
  say "decide-only: $why -> $([ $rc = 0 ] && echo 'would power off' || echo 'no power-off')"; exit 0; fi
say "start dry=$DRY CTP=$CTP OUT=$OUT DEST=$DEST"
svc="$(systemctl show census-batch2.service -p Result -p ExecMainStatus -p ExecMainExitTimestamp 2>/dev/null | tr '\n' ' ')"
say "census-batch2.service: $svc"
rm -rf "$S_"; mkdir -p "$S_/projects" "$S_/ctp" "$S_/logs" || fail "staging dir"
n=0
for d in "$OUT"/*/; do
  name=$(basename "$d"); [ "$name" = .pin-staging ] && continue
  files=$(find "$d" -maxdepth 1 -type f \( -name '*.parquet' -o -name '*.validated' \))
  [ -n "$files" ] || continue
  mkdir -p "$S_/projects/$name"; for f in $files; do cp -l "$f" "$S_/projects/$name/" 2>/dev/null || cp -p "$f" "$S_/projects/$name/" || fail "copy $f"; done; n=$((n+1))
done
say "projects with a Parquet or stamp: $n"
for f in ledger.jsonl ctp.duckdb metrics.tsv resources.tsv runs.log; do [ -f "$CTP/$f" ] && { cp -p "$CTP/$f" "$S_/ctp/" || fail "copy $f"; }; done
( cd "$CTP" && find state -maxdepth 1 -mindepth 1 -type d | while read -r s; do
    mkdir -p "$S_/ctp/$s"; [ -d "$s/logs" ] && cp -a "$s/logs" "$S_/ctp/$s/"; cp -p "$s"/*.json "$S_/ctp/$s/" 2>/dev/null; done ) || fail "copy state"
[ -f "$CLOG" ] && cp -p "$CLOG" "$S_/logs/"
cp -p /data/logs/build.log "$S_/logs/" 2>/dev/null
( cd "$S_" && find . -type f ! -name SHA256SUMS -printf '%P\0' | sort -z | xargs -0 -r sha256sum > SHA256SUMS ) || fail "sha256"
say "staged $(wc -l < "$S_/SHA256SUMS") files, $(du -sh "$S_" | cut -f1)"
aws s3 cp "$S_/" "$DEST/" --recursive --only-show-errors --checksum-algorithm SHA256 || fail "upload"
# Check 1: every staged file is in the bucket with the same size, and nothing else is missing.
( cd "$S_" && find . -type f -printf '%P\t%s\n' | sort ) > /tmp/final.local
aws s3 ls "$DEST/" --recursive | awk -v p="${DEST#s3://*/}/" '{k=$0; sub(/^[^ ]+ +[^ ]+ +[0-9]+ /,"",k); sub("^" p,"",k); print k "\t" $3}' | grep -v -e '^DONE	' -e '^finalize.log	' -e '^FINALIZE_FAILED	' | sort > /tmp/final.remote || fail "list"
missing=$(comm -23 /tmp/final.local /tmp/final.remote | wc -l)
[ "$missing" = 0 ] || { comm -23 /tmp/final.local /tmp/final.remote | head; fail "$missing staged files are missing or differ in size in $DEST"; }
# Check 2: the uploaded SHA256SUMS reads back byte-identical, and the staged files still match it.
aws s3 cp "$DEST/SHA256SUMS" /tmp/final.sums --only-show-errors && cmp /tmp/final.sums "$S_/SHA256SUMS" || fail "SHA256SUMS read-back differs"
( cd "$S_" && sha256sum --quiet -c SHA256SUMS ) || fail "staged files changed during upload"
say "check ok: $(wc -l < /tmp/final.local) objects, sizes equal, SHA256SUMS read back identical"
{ echo "cregit census batch 2 finished and copied: $(date -u +%FT%TZ)"
  echo "instance: $(cat /sys/devices/virtual/dmi/id/board_asset_tag 2>/dev/null)  dry_run=$DRY"
  echo "census-batch2.service: $svc"
  echo "projects copied: $n   files: $(wc -l < "$S_/SHA256SUMS")"
  echo "--- tail of ctp progress"; (cd "$CTP" && CTP_CONFIG=${CTP_CONFIG:-/home/ec2-user/census-batch2.cfg} .venv/bin/python ctp.py progress --manifest ${MANIFEST:-/home/ec2-user/batch2-input/manifest.batch2.tsv} --last 3 2>&1 | head -5)
  echo "--- SHA256SUMS"; cat "$S_/SHA256SUMS"; } > /tmp/DONE
aws s3 cp /tmp/DONE "$DEST/DONE" --only-show-errors && aws s3 ls "$DEST/DONE" >/dev/null || fail "DONE upload"
aws s3 cp "$FLOG" "$DEST/finalize.log" --only-show-errors
say "DONE written to $DEST/DONE"
if [ $DRY = 1 ]; then why=$(/usr/local/bin/census-other-done $SELF 2>&1); rc=$?
  say "dry run: no power-off (a real run would: $why -> $([ $rc = 0 ] && echo 'power off' || echo 'no power-off'))"; exit 0; fi
st=$(systemctl show census-batch2.service -p ExecMainStartTimestampMonotonic --value); ex=$(systemctl show census-batch2.service -p ExecMainExitTimestampMonotonic --value)
ran=$(( (${ex:-0} - ${st:-0}) / 1000000 ))
if [ "$ran" -lt 3600 ]; then say "the census ran only ${ran}s (< 1 h): an early failure, so no power-off; look at $CLOG"; exit 0; fi
if [ -e /home/ec2-user/NO_SHUTDOWN ]; then say "/home/ec2-user/NO_SHUTDOWN exists: no power-off"; exit 0; fi
if ! why=$(/usr/local/bin/census-other-done $SELF 2>&1); then say "$why: no power-off; the other census's finalize powers off"; exit 0; fi
say "$why"
say "powering off (the instance stops; it is not terminated)"
sync; shutdown -h now
EOF_census-batch2-finalize
chmod 755 /usr/local/bin/census-batch2-finalize.new
mv -f /usr/local/bin/census-batch2-finalize.new /usr/local/bin/census-batch2-finalize
cat > /usr/local/bin/census-batch3L-finalize.new <<'EOF_census-batch3L-finalize'
#!/usr/bin/env bash
# Runs when census-batch3L.service exits (OnSuccess=/OnFailure=). Copies the results to
# s3://BUCKET/batch3L/final/, checks every object (key and size) and SHA256SUMS against the
# local files, writes DONE, then powers off (the instance STOPS; the RAID0 is lost).
# No power-off if the check fails, with --dry-run, if the census ran < 1 h, if
# /home/ec2-user/NO_SHUTDOWN exists, or (2026-10-09) if the other census on this instance
# (batch 2 / batch 3L) has not finalized: census-other-done decides; the second one to
# finalize powers off.
# --dry-run: copy to batch3L/dryrun/ from CTP/OUT given in the environment, never power off.
# --decide-only: print only the power-off decision (census-other-done), copy nothing.
set -uo pipefail
SELF=batch3L
DRY=0; [ "${1:-}" = --dry-run ] && DRY=1
DECIDE=0; [ "${1:-}" = --decide-only ] && DECIDE=1
B=s3://${RUNNER_BUCKET}
CTP=${CTP:-/home/ec2-user/ctp-b3L}
OUT=${OUT:-/data/census-2026-10-batch3L}
CLOG=${CLOG:-/data/logs/batch3L.log}
DEST=${DEST:-$B/batch3L/final}; [ $DRY = 1 ] && DEST=${DEST_DRY:-$B/batch3L/dryrun}
S_=/data/final-stage-batch3L; FLOG=/data/logs/finalize-batch3L.log
TM=$(mktemp -d /tmp/finalize-batch3L.XXXXXX)
exec > >(tee -a "$FLOG") 2>&1
say() { echo "[$(date -u +%FT%TZ)] finalize: $*"; }
fail() { say "FAILED: $*"; echo "finalize failed at $(date -u +%FT%TZ): $*" > $TM/FINALIZE_FAILED
         aws s3 cp $TM/FINALIZE_FAILED "$DEST/FINALIZE_FAILED" --only-show-errors; aws s3 cp "$FLOG" "$DEST/finalize.log" --only-show-errors; exit 1; }
if [ $DECIDE = 1 ]; then why=$(/usr/local/bin/census-other-done $SELF 2>&1); rc=$?
  say "decide-only: $why -> $([ $rc = 0 ] && echo 'would power off' || echo 'no power-off')"; exit 0; fi
say "start dry=$DRY CTP=$CTP OUT=$OUT DEST=$DEST"
svc="$(systemctl show census-batch3L.service -p Result -p ExecMainStatus -p ExecMainExitTimestamp 2>/dev/null | tr '\n' ' ')"
say "census-batch3L.service: $svc"
rm -rf "$S_"; mkdir -p "$S_/projects" "$S_/ctp" "$S_/logs" || fail "staging dir"
n=0
for d in "$OUT"/*/; do
  name=$(basename "$d"); [ "$name" = .pin-staging ] && continue
  files=$(find "$d" -maxdepth 1 -type f \( -name '*.parquet' -o -name '*.validated' \))
  [ -n "$files" ] || continue
  mkdir -p "$S_/projects/$name"; for f in $files; do cp -l "$f" "$S_/projects/$name/" 2>/dev/null || cp -p "$f" "$S_/projects/$name/" || fail "copy $f"; done; n=$((n+1))
done
say "projects with a Parquet or stamp: $n"
for f in ledger.jsonl ctp.duckdb metrics.tsv resources.tsv runs.log; do [ -f "$CTP/$f" ] && { cp -p "$CTP/$f" "$S_/ctp/" || fail "copy $f"; }; done
( cd "$CTP" && find state -maxdepth 1 -mindepth 1 -type d | while read -r s; do
    mkdir -p "$S_/ctp/$s"; [ -d "$s/logs" ] && cp -a "$s/logs" "$S_/ctp/$s/"; cp -p "$s"/*.json "$S_/ctp/$s/" 2>/dev/null; done ) || fail "copy state"
[ -f "$CLOG" ] && cp -p "$CLOG" "$S_/logs/"
cp -p /data/logs/build.log "$S_/logs/" 2>/dev/null
( cd "$S_" && find . -type f ! -name SHA256SUMS -printf '%P\0' | sort -z | xargs -0 -r sha256sum > SHA256SUMS ) || fail "sha256"
say "staged $(wc -l < "$S_/SHA256SUMS") files, $(du -sh "$S_" | cut -f1)"
aws s3 cp "$S_/" "$DEST/" --recursive --only-show-errors --checksum-algorithm SHA256 || fail "upload"
# Check 1: every staged file is in the bucket with the same size, and nothing else is missing.
( cd "$S_" && find . -type f -printf '%P\t%s\n' | sort ) > $TM/final.local
aws s3 ls "$DEST/" --recursive | awk -v p="${DEST#s3://*/}/" '{k=$0; sub(/^[^ ]+ +[^ ]+ +[0-9]+ /,"",k); sub("^" p,"",k); print k "\t" $3}' | grep -v -e '^DONE	' -e '^finalize.log	' -e '^FINALIZE_FAILED	' | sort > $TM/final.remote || fail "list"
missing=$(comm -23 $TM/final.local $TM/final.remote | wc -l)
[ "$missing" = 0 ] || { comm -23 $TM/final.local $TM/final.remote | head; fail "$missing staged files are missing or differ in size in $DEST"; }
# Check 2: the uploaded SHA256SUMS reads back byte-identical, and the staged files still match it.
aws s3 cp "$DEST/SHA256SUMS" $TM/final.sums --only-show-errors && cmp $TM/final.sums "$S_/SHA256SUMS" || fail "SHA256SUMS read-back differs"
( cd "$S_" && sha256sum --quiet -c SHA256SUMS ) || fail "staged files changed during upload"
say "check ok: $(wc -l < $TM/final.local) objects, sizes equal, SHA256SUMS read back identical"
{ echo "cregit census batch 3L finished and copied: $(date -u +%FT%TZ)"
  echo "instance: $(cat /sys/devices/virtual/dmi/id/board_asset_tag 2>/dev/null)  dry_run=$DRY"
  echo "census-batch3L.service: $svc"
  echo "projects copied: $n   files: $(wc -l < "$S_/SHA256SUMS")"
  echo "--- tail of ctp progress"; (cd "$CTP" && CTP_CONFIG=${CTP_CONFIG:-/home/ec2-user/census-batch3L.cfg} .venv/bin/python ctp.py progress --manifest ${MANIFEST:-/home/ec2-user/batch3L-input/manifest.batch3L.tsv} --last 3 2>&1 | head -5)
  echo "--- SHA256SUMS"; cat "$S_/SHA256SUMS"; } > $TM/DONE
aws s3 cp $TM/DONE "$DEST/DONE" --only-show-errors && aws s3 ls "$DEST/DONE" >/dev/null || fail "DONE upload"
aws s3 cp "$FLOG" "$DEST/finalize.log" --only-show-errors
say "DONE written to $DEST/DONE"
if [ $DRY = 1 ]; then why=$(/usr/local/bin/census-other-done $SELF 2>&1); rc=$?
  say "dry run: no power-off (a real run would: $why -> $([ $rc = 0 ] && echo 'power off' || echo 'no power-off'))"; exit 0; fi
st=$(systemctl show census-batch3L.service -p ExecMainStartTimestampMonotonic --value); ex=$(systemctl show census-batch3L.service -p ExecMainExitTimestampMonotonic --value)
ran=$(( (${ex:-0} - ${st:-0}) / 1000000 ))
if [ "$ran" -lt 3600 ]; then say "the census ran only ${ran}s (< 1 h): an early failure, so no power-off; look at $CLOG"; exit 0; fi
if [ -e /home/ec2-user/NO_SHUTDOWN ]; then say "/home/ec2-user/NO_SHUTDOWN exists: no power-off"; exit 0; fi
if ! why=$(/usr/local/bin/census-other-done $SELF 2>&1); then say "$why: no power-off; the other census's finalize powers off"; exit 0; fi
say "$why"
say "powering off (the instance stops; it is not terminated)"
sync; shutdown -h now
EOF_census-batch3L-finalize
chmod 755 /usr/local/bin/census-batch3L-finalize.new
mv -f /usr/local/bin/census-batch3L-finalize.new /usr/local/bin/census-batch3L-finalize
cat > /usr/local/bin/census-batch3L-wait.new <<'EOF_census-batch3L-wait'
#!/usr/bin/env bash
# census-batch3L-wait.service: start census-batch3L.service only when batch 2 frees slots.
# Every 60 s: start when census-batch2 is no longer active, or when batch 2 has no project left
# that it has not started (in its current run) AND batch 2 runs at most SLOTS - W projects,
# where W is the number of batch3L projects. So the two censuses together run <= SLOTS (20).
# A STOP file in the batch3L ctp clone holds the start. Status: /run/census-batch3L-wait.status.
set -uo pipefail
SLOTS=${SLOTS:-20}
M2=/home/ec2-user/batch2-input/manifest.batch2.tsv
M3=/home/ec2-user/batch3L-input/manifest.batch3L.tsv
W=$(grep -c -v -e '^#' -e '^[[:space:]]*$' "$M3")
ST=/run/census-batch3L-wait.status
while :; do
  now=$(date -u +%FT%TZ); b2=$(systemctl is-active census-batch2.service)
  read -r run2 pend2 < <(/usr/local/bin/census-steps --counts /home/ec2-user/ctp "$M2" 2>/dev/null || echo "? ?")
  msg="$now waiting: census-batch2 $b2, batch 2 running $run2, not started $pend2; batch3L needs $W of $SLOTS slots"
  if [ -e /home/ec2-user/ctp-b3L/STOP ]; then
    echo "$msg; STOP exists in /home/ec2-user/ctp-b3L: holding" | tee "$ST"
  elif [ "$b2" != active ] && [ "$b2" != activating ] || { [ "$pend2" = 0 ] && [ "$run2" != "?" ] && [ $((run2 + W)) -le "$SLOTS" ]; }; then
    echo "$now starting census-batch3L.service (census-batch2 $b2, batch 2 running $run2, not started $pend2)" | tee "$ST"
    systemctl start --no-block census-batch3L.service
    exit 0
  else
    echo "$msg" > "$ST"
  fi
  sleep 60
done
EOF_census-batch3L-wait
chmod 755 /usr/local/bin/census-batch3L-wait.new
mv -f /usr/local/bin/census-batch3L-wait.new /usr/local/bin/census-batch3L-wait
cat > /usr/local/bin/census-batch3L-run.new <<'EOF_census-batch3L-run'
#!/usr/bin/env bash
# Census batch 3L (the 5 L projects of batch 3) on the batch 2 instance, after batch 2 has
# started all its projects (census-batch3L-wait). Own ctp clone, config and output; the same
# cregit build /data/cregit-ec2 and the same flags as batch 2, except the manifest and --workers.
# Stop after the running projects: touch /home/ec2-user/ctp-b3L/STOP. Resume: start the unit again.
set -euo pipefail
I=/home/ec2-user/batch3L-input
export CTP_CONFIG=/home/ec2-user/census-batch3L.cfg
cd /home/ec2-user/ctp-b3L
W=$(grep -c -v -e '^#' -e '^[[:space:]]*$' "$I/manifest.batch3L.tsv")
echo "=== $(date -u +%FT%TZ) census-batch3L start (cregit $(git -C /data/cregit-ec2 rev-parse --short HEAD), ctp $(git rev-parse --short HEAD), workers $W)"
exec .venv/bin/python ctp.py census --manifest "$I/manifest.batch3L.tsv" \
    --project-meta "$I/project_meta.batch3L.json" \
    --workers "$W" --retries 3 --skip-html --latest --tokenizer-worker \
    --blame-jobs 4 --memory-limit 8GB --min-free-mem-gb 24 --disk-floor-gb 500
EOF_census-batch3L-run
chmod 755 /usr/local/bin/census-batch3L-run.new
mv -f /usr/local/bin/census-batch3L-run.new /usr/local/bin/census-batch3L-run
cat > /usr/local/bin/census-batch3L-live.new <<'EOF_census-batch3L-live'
#!/usr/bin/env bash
# Every 10 min (census-batch3L-live.timer): status of census batch 3L to s3://BUCKET/batch3L/live/.
set -uo pipefail
D=s3://${RUNNER_BUCKET}/batch3L/live
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export CTP_CONFIG=/home/ec2-user/census-batch3L.cfg
C=/home/ec2-user/ctp-b3L; M=/home/ec2-user/batch3L-input/manifest.batch3L.tsv
/usr/local/bin/census-steps "$C" "$M" --highlight '' > "$T/steps.txt" 2>&1
{ echo "as of $(date -u +%FT%TZ)  census-batch3L: $(systemctl is-active census-batch3L.service) ($(systemctl show census-batch3L.service -p Result --value))  waiter: $(systemctl is-active census-batch3L-wait.service)"
  echo "waiter status: $(cat /run/census-batch3L-wait.status 2>/dev/null || echo none)"
  echo "census-batch2: $(systemctl is-active census-batch2.service)"
  echo "uptime: $(uptime)"
  echo "MemAvailable: $(awk '/MemAvailable/{printf "%.1f GiB", $2/1048576}' /proc/meminfo)   /data free: $(df -BG --output=avail /data | tail -1 | tr -d ' ')"
  echo
  (cd "$C" && .venv/bin/python ctp.py progress --manifest "$M" --last 10 2>&1)
  echo; echo "=== steps"; cat "$T/steps.txt"
} > "$T/progress.txt"
tail -n 300 /data/logs/batch3L.log > "$T/batch3L.log.tail" 2>/dev/null || true
{ date -u +%FT%TZ; uptime; cat /proc/meminfo; df -h /data /; } > "$T/system.txt"
[ -f "$C/ledger.jsonl" ] && cp "$C/ledger.jsonl" "$T/ledger.jsonl"
aws s3 cp "$T/" "$D/" --recursive --only-show-errors
EOF_census-batch3L-live
chmod 755 /usr/local/bin/census-batch3L-live.new
mv -f /usr/local/bin/census-batch3L-live.new /usr/local/bin/census-batch3L-live
cat > /etc/systemd/system/census-batch3L.service.new <<'EOF_census-batch3L.service'
[Unit]
Description=cregit census batch 3L (ctp census, the L projects of batch 3)
Wants=network-online.target
After=network-online.target nix-daemon.service
RequiresMountsFor=/data
OnSuccess=census-batch3L-finalize.service
OnFailure=census-batch3L-finalize.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/home/ec2-user/ctp-b3L
ExecStart=/usr/local/bin/census-batch3L-run
StandardOutput=append:/data/logs/batch3L.log
StandardError=append:/data/logs/batch3L.log
Restart=no
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStopSec=300
EOF_census-batch3L.service
chmod 644 /etc/systemd/system/census-batch3L.service.new
mv -f /etc/systemd/system/census-batch3L.service.new /etc/systemd/system/census-batch3L.service
cat > /etc/systemd/system/census-batch3L-finalize.service.new <<'EOF_census-batch3L-finalize.service'
[Unit]
Description=cregit census batch 3L: copy results to S3, write DONE, power off
RequiresMountsFor=/data

[Service]
Type=oneshot
ExecStart=/usr/local/bin/census-batch3L-finalize
TimeoutStartSec=infinity
EOF_census-batch3L-finalize.service
chmod 644 /etc/systemd/system/census-batch3L-finalize.service.new
mv -f /etc/systemd/system/census-batch3L-finalize.service.new /etc/systemd/system/census-batch3L-finalize.service
cat > /etc/systemd/system/census-batch3L-wait.service.new <<'EOF_census-batch3L-wait.service'
[Unit]
Description=cregit census batch 3L: wait until batch 2 frees slots, then start census-batch3L
After=network-online.target
RequiresMountsFor=/data

[Service]
Type=simple
ExecStart=/usr/local/bin/census-batch3L-wait
Restart=on-failure
RestartSec=60
EOF_census-batch3L-wait.service
chmod 644 /etc/systemd/system/census-batch3L-wait.service.new
mv -f /etc/systemd/system/census-batch3L-wait.service.new /etc/systemd/system/census-batch3L-wait.service
cat > /etc/systemd/system/census-batch3L-live.service.new <<'EOF_census-batch3L-live.service'
[Unit]
Description=cregit census batch 3L: live status to S3

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/census-batch3L-live
TimeoutStartSec=300
EOF_census-batch3L-live.service
chmod 644 /etc/systemd/system/census-batch3L-live.service.new
mv -f /etc/systemd/system/census-batch3L-live.service.new /etc/systemd/system/census-batch3L-live.service
cat > /etc/systemd/system/census-batch3L-live.timer.new <<'EOF_census-batch3L-live.timer'
[Unit]
Description=cregit census batch 3L: live status to S3 every 10 min

[Timer]
OnActiveSec=1min
OnUnitActiveSec=10min
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF_census-batch3L-live.timer
chmod 644 /etc/systemd/system/census-batch3L-live.timer.new
mv -f /etc/systemd/system/census-batch3L-live.timer.new /etc/systemd/system/census-batch3L-live.timer
