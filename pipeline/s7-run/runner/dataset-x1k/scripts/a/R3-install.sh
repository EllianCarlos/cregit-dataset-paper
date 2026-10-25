#!/usr/bin/env bash
# R3-install.sh, machine A (the x1k long rows; root, through scripts/a/ssm-a.sh; idempotent; starts
# nothing). The full v1 pipeline (user decision 2026-10-19: the x1k rows join the dataset): ctp
# ca113e3 without a patch, the flags of the v1 fed parts, with the firm step, validate and join.
# One ctp run (ctp.py census, one-row manifest) per project, each in its own tree /dataK/x1k/<p>
# (link /data/x1k-long/<p>):
#   x1k-long@<p>.service  x1k-long-run <p>: ctp.py census with the one-row manifest of <p>. At each
#                         start it reads the last completed step L from out/<p>/pipeline.log: L 6-9
#                         -> --from-step L+1; L 10 with the Parquet -> --from-step 11 (the runner
#                         does nothing; firm, validate, schema, join and cleanup run); else no
#                         --from-step (ctp resumes step 2). It removes the orphans of a killed
#                         attempt first (cregit blameRepo/build/tmpfile-*, step-10 sync_*.db and
#                         duckdb_temp_*, firm .<p>-dataset.parquet.firm-tmp and .firm-spill/*)
#                         and a STOP file left by x1k-long-watch. KillMode=mixed: a stop sends
#                         SIGTERM to ctp only, then SIGKILL to all (as a reclaim; the runner's
#                         FROM_STEP=1 failure trap does not run).
#   x1k-long-upload.timer every 2 min: each finished project to s3://B/dataset-x1k/done-full/<p>/ +
#                         OK (the full done set, as machines B; part = "a"; never into a prefix
#                         that has an OK).
#   x1k-long-live.timer   every 10 min: s3://B/dataset-x1k/live-a/progress.txt.
#   x1k-long-watch        spot notice -> STOP in every tree, ledgers + INTERRUPTED to live-a/, sync,
#                         one upload. The EBS volumes keep the work (DeleteOnTermination false).
#   x1k-long-finalize     when all units of /data/x1k-long/run.list are inactive: ledgers and logs
#                         to s3://B/dataset-x1k/final-a/<p>/, size check, final-a/DONE, then (no
#                         NO_SHUTDOWN, no /run/x1k-hold, up >= 1 h) shutdown -h: the instance
#                         terminates, the volumes stay (the user deletes them after the check).
#                         A row in /data/x1k-long/excluded.tsv ("<p><TAB><reason>", on volume 1;
#                         2026-10-20: the 2 no-token rows) needs no upload, only "census finished".
set -euo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}) echo "ABORT: $IID is spot a or the big EC2"; exit 1 ;; esac
mkdir -p /etc/dataset-x1k
cat > /usr/local/bin/x1k-long-run.new <<'EOF_x1k_long_run'
#!/usr/bin/env bash
# x1k-long-run P (x1k-long@P.service, ec2-user): ctp.py census for project P in its own tree.
# Tree: X1K_TREE (default /data/x1k-long/P) with ctp/ (ca113e3, clean), cregit-ec2/ (57551d7),
# out/, logs/, ctp.cfg, manifest.tsv (one row) and run.env (R4: JOBS MEM MINFREE DISKFLOOR RETRIES
# META LATEST). Resume rule: L = the last step with a "✓ completed" line in the newest attempt of
# out/P/pipeline.log (an attempt starts where a step heading is not above the one before).
# L >= 10 and the Parquet exists -> --from-step 11 (firm and the later phases only); L >= 10
# without it -> 10; L >= 6 -> --from-step L+1 (keeps blame/; cregit skips each finished .blame);
# else no --from-step (ctp auto-resume: step 2 after drop_derived, or 1).
set -euo pipefail
P=${1:?project}
T=$(readlink -f "${X1K_TREE:-/data/x1k-long/$P}")
. "$T/run.env"
C=$T/ctp; W=$T/out/$P; LOG=$W/pipeline.log; BB=$T/cregit-ec2/blameRepo/build
export CTP_CONFIG=$T/ctp.cfg
cd "$C"
[ "$(git rev-parse --short HEAD)" = ca113e3 ] && [ -z "$(git status --porcelain --untracked-files=no)" ] \
  || { echo "ctp of $P is not the clean ca113e3 (the v1 code)"; exit 2; }
if [ -e STOP ]; then echo "removing $C/STOP of $(stat -c %y STOP) (ctp.py census exits at once if it exists)"; rm -f STOP; fi
last=0
[ -f "$LOG" ] && last=$(awk 'index(prev, "═══") == 1 && $0 ~ /^  Step [0-9]+ / { s = $2 + 0; if (h == 0 || s <= h) last = s - 1; h = s }
    index($0, "  ✓ completed in ") == 1 && h { last = h }
    { prev = $0 }
    END { print last + 0 }' "$LOG")
if [ "$last" -ge 10 ] && [ -f "$W/$P-dataset.parquet" ]; then from=11; elif [ "$last" -ge 10 ]; then from=10; elif [ "$last" -ge 6 ]; then from=$((last + 1)); else from=1; fi
need=""
[ "$from" -ge 7 ] && [ ! -d "$W/$P-cregit" ] && need="$need $P-cregit"
[ "$from" -ge 8 ] && [ ! -d "$W/blame" ] && need="$need blame"
[ "$from" -ge 9 ] && for f in "$P-cregit.db" "$P-original.db"; do [ -f "$W/$f" ] || need="$need $f"; done
if [ -n "$need" ]; then echo "last completed step $last, but missing in $W:$need; no --from-step instead"; from=1; fi
nt=$(find "$BB" -maxdepth 1 -name 'tmpfile-*' 2>/dev/null | wc -l)
find "$BB" -maxdepth 1 -name 'tmpfile-*' -delete 2>/dev/null || true
ns=0
if [ -d "$W" ]; then
  ns=$(find "$W" -maxdepth 1 \( -name 'sync_*.db' -o -name 'duckdb_temp_*' -o -name ".$P-dataset.parquet.firm-tmp" \) | wc -l)
  find "$W" -maxdepth 1 \( -name 'sync_*.db' -o -name 'duckdb_temp_*' -o -name ".$P-dataset.parquet.firm-tmp" \) -exec rm -f {} + 2>/dev/null || true
  if [ -d "$W/.firm-spill" ]; then ns=$((ns + $(find "$W/.firm-spill" -mindepth 1 | wc -l))); find "$W/.firm-spill" -mindepth 1 -delete; fi
fi
args=(--manifest "$T/manifest.tsv" --project-meta "$META" --workers 1 --retries "$RETRIES" --skip-html
      ${LATEST:+"$LATEST"} --tokenizer-worker --blame-jobs "$JOBS" --memory-limit "$MEM"
      --min-free-mem-gb "$MINFREE" --disk-floor-gb "$DISKFLOOR")
[ "$from" -gt 1 ] && args+=(--from-step "$from")
echo "=== $(date -u +%FT%TZ) x1k-long $P start on $(cat /sys/devices/virtual/dmi/id/board_asset_tag 2>/dev/null || hostname)" \
     "(cregit $(git -C "$T/cregit-ec2" rev-parse --short HEAD), ctp $(git rev-parse --short HEAD), full pipeline):" \
     "last completed step $last, from-step $from, removed $nt tmpfile-* and $ns step-10/firm scratch files;" \
     "blame-jobs $JOBS, memory-limit $MEM, retries $RETRIES"
exec .venv/bin/python ctp.py census "${args[@]}"
EOF_x1k_long_run
cat > /usr/local/bin/x1k-long-upload.new <<'EOF_x1k_long_upload'
#!/usr/bin/env python3
"""x1k-long-upload (x1k-long-upload.timer, ec2-user): copy each finished long-row project to S3.

The same rules as x1k-upload of the light-row machine, for the trees /data/x1k-long/<p>: a project
is finished when its last final ledger row says done or done-dirty and its .validated stamp exists.
Copies the Parquet, the stamp, the persons DB (if any), ctp state/<p>/*.json and state/<p>/logs/*,
and the ledger rows of <p>, to s3://BUCKET/dataset-x1k/done-full/<p>/ (the full done set), compares
every key and size, then writes done-full/<p>/OK and the local marker <tree>/uploaded/<p>. It never
writes into a done-full/<p>/ that has an OK already (it reports it and writes no marker).
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEST = "s3://${RUNNER_BUCKET}/dataset-x1k/done-full"
ROOT = Path("/data/x1k-long")


def finished(ctp):
    final, rows = {}, {}
    try:
        with (ctp / "ledger.jsonl").open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                p = r.get("project")
                if p:
                    rows.setdefault(p, []).append(line)
                if r.get("step") == "project" and p:
                    final[p] = r.get("state")
    except OSError:
        return [], {}
    return [p for p, s in final.items() if s in ("done", "done-dirty")], rows


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def upload(name, tree, rows):
    ctp, out = tree / "ctp", tree / "out"
    pq = out / name / f"{name}-dataset.parquet"
    stamp = out / name / f"{name}.validated"
    if not (pq.is_file() and stamp.is_file()):
        return f"{name}: Parquet or stamp missing, later"
    have = subprocess.run(["aws", "s3", "ls", f"{DEST}/{name}/OK"], capture_output=True, text=True)
    if have.returncode == 0 and have.stdout.strip():
        return f"{name}: {DEST}/{name}/OK exists already; not written over (check by hand)"
    stage = tree / "upload-stage"  # same filesystem as out/, so os.link works
    stage.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}.", dir=stage))
    try:
        for f in (pq, stamp):
            os.link(f, tmp / f.name)
        persons = out / name / f"{name}-persons.db"
        if persons.is_file():
            os.link(persons, tmp / persons.name)
        st = ctp / "state" / name
        (tmp / "state" / "logs").mkdir(parents=True)
        for f in st.glob("*.json"):
            if f.is_file() and not f.is_symlink():
                shutil.copy2(f, tmp / "state" / f.name)
        for f in (st / "logs").glob("*"):
            if f.is_file() and not f.is_symlink():
                shutil.copy2(f, tmp / "state" / "logs" / f.name)
        (tmp / "ledger.rows.jsonl").write_text("".join(rows.get(name, [])))
        local = {str(p.relative_to(tmp)): p.stat().st_size for p in tmp.rglob("*") if p.is_file()}
        subprocess.run(["aws", "s3", "cp", f"{tmp}/", f"{DEST}/{name}/", "--recursive",
                        "--only-show-errors"], check=True)
        ls = subprocess.run(["aws", "s3", "ls", f"{DEST}/{name}/", "--recursive"], check=True,
                            capture_output=True, text=True).stdout
        prefix = DEST.split("/", 3)[3] + f"/{name}/"
        remote = {}
        for line in ls.splitlines():
            c = line.split(None, 3)
            if len(c) == 4 and c[3].startswith(prefix):
                remote[c[3][len(prefix):]] = int(c[2])
        bad = [key for key, v in local.items() if remote.get(key) != v]
        if bad:
            return f"{name}: size check FAILED for {bad[:5]}, will retry"
        ok = tmp / "OK"
        instance = Path("/sys/devices/virtual/dmi/id/board_asset_tag").read_text().strip()
        ok.write_text(f"uploaded {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} from {instance} part a\n"
                      f"parquet_sha256 {sha256(pq)}\n"
                      + "".join(f"{v}\t{key}\n" for key, v in sorted(local.items())))
        subprocess.run(["aws", "s3", "cp", str(ok), f"{DEST}/{name}/OK", "--only-show-errors"], check=True)
        (tree / "uploaded").mkdir(parents=True, exist_ok=True)
        (tree / "uploaded" / name).write_text(ok.read_text())
        return f"{name}: uploaded {len(local)} files, sizes equal, OK written"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for link in sorted(ROOT.iterdir()) if ROOT.is_dir() else []:
        tree = link.resolve()
        if not (tree / "ctp").is_dir():
            continue
        names, rows = finished(tree / "ctp")
        for name in names:
            if (tree / "uploaded" / name).exists():
                continue
            try:
                print(time.strftime("%FT%TZ", time.gmtime()), upload(name, tree, rows), flush=True)
            except (subprocess.CalledProcessError, OSError) as x:
                print(time.strftime("%FT%TZ", time.gmtime()), f"{name}: upload error {x}, will retry", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
EOF_x1k_long_upload
cat > /usr/local/bin/x1k-long-status.new <<'EOF_x1k_long_status'
#!/usr/bin/env bash
# x1k-long-status (any user, read-only): one block per project of /data/x1k-long/run.list: unit,
# step now, last completed step, .blame files and the files that step 7 of this attempt started
# (cregit prints no total before the end), PLAIN-BLAME lines,
# orphan tmpfile-*, upload; then free space per volume and memory. Used by x1k-long-live and C1.
set -uo pipefail
L=/data/x1k-long
echo "x1k long rows $(date -u +%FT%TZ) on $(cat /sys/devices/virtual/dmi/id/board_asset_tag), up $(awk '{printf "%.1f h", $1/3600}' /proc/uptime); $(cat $L/started 2>/dev/null || echo 'not started')"
n=0; u=0
for p in $(cat $L/run.list 2>/dev/null); do T=$(readlink -f $L/$p); W=$T/out/$p; G=$W/pipeline.log; n=$((n + 1))
  [ -e $T/uploaded/$p ] && u=$((u + 1))
  st=$(awk 'index(prev, "═══") == 1 && $0 ~ /^  Step [0-9]+ / { s = $2 + 0; if (h == 0 || s <= h) last = s - 1; h = s }
      index($0, "  ✓ completed in ") == 1 && h { last = h }
      { prev = $0 }
      END { printf "step now %d, last completed %d", h, last }' $G 2>/dev/null)
  nb=$(find $W/blame -name '*.blame' 2>/dev/null | wc -l)
  nf=$(awk 'index(prev, "═══") == 1 && /^  Step 7 / { n = 0; on = 1 } index(prev, "═══") == 1 && /^  Step [89] / { on = 0 }
      on && /^[0-9]+: / { n++ } { prev = $0 } END { print n + 0 }' $G 2>/dev/null)
  pb=$(grep -c '^PLAIN-BLAME' $G 2>/dev/null); tf=$(find $T/cregit-ec2/blameRepo/build -maxdepth 1 -name 'tmpfile-*' 2>/dev/null | wc -l)
  ph=$(python3 -c 'import json, sys
r = None
for l in open(sys.argv[1]):
    try: x = json.loads(l)
    except ValueError: continue
    if x.get("project") == sys.argv[2]: r = x
print("ctp", r.get("step"), r.get("state")) if r else print("ctp no row")' $T/ctp/ledger.jsonl $p 2>/dev/null)
  echo "--- $p (/$(echo $T | cut -d/ -f2)): unit $(systemctl is-active x1k-long@$p); ${ph:-ctp no ledger}; ${st:-no pipeline.log}; .blame files $nb (step 7 of this attempt started ${nf:-0}); PLAIN-BLAME ${pb:-0}; tmpfile-* $tf; $([ -e $T/uploaded/$p ] && echo uploaded || echo 'not uploaded'); out $(du -sh $W 2>/dev/null | cut -f1)"
  grep -v '^\s*$' $T/logs/run.log 2>/dev/null | tail -1 | cut -c1-200
done
echo "=== uploaded $u of $n"
df -h --output=target,size,used,avail,pcent /data1 /data2 /data3 /data4 2>/dev/null
free -g | sed -n 2p; uptime
[ -e /run/x1k-spot-interrupted ] && echo "SPOT INTERRUPTION: $(cat /run/x1k-spot-interrupted)"
[ -f /etc/dataset-x1k/final-a-DONE ] && cat /etc/dataset-x1k/final-a-DONE
exit 0
EOF_x1k_long_status
cat > /usr/local/bin/x1k-long-live.new <<'EOF_x1k_long_live'
#!/usr/bin/env bash
# x1k-long-live (x1k-long-live.timer, ec2-user): x1k-long-status to s3://B/dataset-x1k/live-a/progress.txt.
set -uo pipefail
T=$(mktemp)
/usr/local/bin/x1k-long-status > $T 2>&1
aws s3 cp $T s3://${RUNNER_BUCKET}/dataset-x1k/live-a/progress.txt --only-show-errors
rm -f $T
EOF_x1k_long_live
cat > /usr/local/bin/x1k-long-watch.new <<'EOF_x1k_long_watch'
#!/usr/bin/env bash
# x1k-long-watch (x1k-long-watch.service, root): poll IMDSv2 spot/instance-action every 5 s. On a
# notice: /run/x1k-spot-interrupted, STOP in every tree's ctp clone, each ledger and INTERRUPTED to
# s3://B/dataset-x1k/live-a/, sync (the EBS volumes keep the rest), one x1k-long-upload. Recovery:
# ~/s3-work/dataset-x1k/README.md, "Machine A runbook", reclaim.
set -uo pipefail
B=s3://${RUNNER_BUCKET}
IMDS=http://169.254.169.254/latest
L=/data/x1k-long
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
echo "$(date -u +%FT%TZ) watching $IMDS/meta-data/spot/instance-action every 5 s"
while :; do
  tok=$(curl -s -m 2 -X PUT "$IMDS/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
  if [ -n "$tok" ]; then
    code=$(curl -s -m 2 -o /run/x1k-instance-action -w '%{http_code}' -H "X-aws-ec2-metadata-token: $tok" "$IMDS/meta-data/spot/instance-action")
    if [ "$code" = 200 ]; then
      echo "$(date -u +%FT%TZ) $(cat /run/x1k-instance-action)" > /run/x1k-spot-interrupted
      T=$(mktemp -d)
      for p in $(cat $L/run.list); do C=$L/$p/ctp; touch $C/STOP; chown ec2-user: $C/STOP
        [ -f $C/ledger.jsonl ] && cp $C/ledger.jsonl $T/ledger.$p.jsonl; done
      sync
      { echo "spot interruption notice seen $(date -u +%FT%TZ) on $IID"; cat /run/x1k-instance-action; echo
        /usr/local/bin/x1k-long-status; } > $T/INTERRUPTED 2>&1
      aws s3 cp $T/ $B/dataset-x1k/live-a/ --recursive --only-show-errors
      sudo -u ec2-user /usr/local/bin/x1k-long-upload
      sync
      echo "real notice handled; idle until termination"; exec sleep infinity
    fi
  fi
  sleep 5
done
EOF_x1k_long_watch
cat > /usr/local/bin/x1k-long-finalize.new <<'EOF_x1k_long_finalize'
#!/usr/bin/env bash
# x1k-long-finalize (root; after each unit ends and every 15 min): see R3-install.sh of machine A.
set -uo pipefail
B=s3://${RUNNER_BUCKET}
E=/etc/dataset-x1k; L=/data/x1k-long
# excluded.tsv (on volume 1; "<p><TAB><reason>"): rows that end without an upload by decision
# (2026-10-20: no tokens). Such a row counts as finished when its unit wrote "census finished".
X=$L/excluded.tsv
excluded() { [ -f $X ] && cut -f1 $X | grep -q -x -F "$1"; }
[ -f $L/started ] && [ -f $L/run.list ] || exit 0
[ -e /run/x1k-spot-interrupted ] && exit 0
for p in $(cat $L/run.list); do systemctl is-active -q x1k-long@$p && exit 0; done
[ -f $E/final-a-DONE ] && exit 0
echo "$(date -u +%FT%TZ) all units inactive: final upload"
sudo -u ec2-user /usr/local/bin/x1k-long-upload
clean=1; T=$(mktemp -d)
for p in $(cat $L/run.list); do R=$(readlink -f $L/$p); C=$R/ctp; mkdir -p $T/$p
  grep -q 'census finished rc=' $R/logs/run.log 2>/dev/null || clean=0
  [ -e $R/uploaded/$p ] || excluded $p || clean=0
  for f in ledger.jsonl runs.log metrics.tsv resources.tsv; do [ -f $C/$f ] && cp $C/$f $T/$p/; done
  cp $R/logs/run.log $R/manifest.tsv $R/run.env $T/$p/ 2>/dev/null
  [ -f $R/out/$p/pipeline.log ] && cp $R/out/$p/pipeline.log $T/$p/
  [ -e $R/uploaded/$p ] || (cd $C/state 2>/dev/null && tar -czf $T/$p/state-not-uploaded.tar.gz $p 2>/dev/null)
done
/usr/local/bin/x1k-long-status > $T/status.txt 2>&1
[ -f $X ] && cp $X $T/excluded.tsv
aws s3 cp $T/ $B/dataset-x1k/final-a/ --recursive --only-show-errors
ok=1
for f in $(cd $T && find . -type f | sed 's|^\./||'); do
  s=$(aws s3 ls $B/dataset-x1k/final-a/$f | awk '{print $3}')
  [ "$s" = "$(stat -c %s $T/$f)" ] || { ok=0; echo "size check failed: $f"; }
done
if [ $ok = 1 ] && [ $clean = 1 ]; then
  { echo "x1k long rows final $(date -u +%FT%TZ) on $(cat /sys/devices/virtual/dmi/id/board_asset_tag)"
    for p in $(cat $L/run.list); do echo "$p: $([ -e $L/$p/uploaded/$p ] && echo uploaded || echo "excluded ($(grep -P "^$p\t" $X | cut -f2 | cut -c1-120))"); $(grep 'census finished rc=' $T/$p/run.log | tail -1 | cut -c1-160)"; done
  } > $T/DONE
  aws s3 cp $T/DONE $B/dataset-x1k/final-a/DONE --only-show-errors && cp $T/DONE $E/final-a-DONE
  cat $T/DONE
  up=$(awk '{print int($1)}' /proc/uptime)
  if [ -e /home/ec2-user/NO_SHUTDOWN ] || [ -e /run/x1k-hold ] || [ "$up" -lt 3600 ]; then
    echo "no shutdown (NO_SHUTDOWN, /run/x1k-hold or up < 1 h)"
  else
    sync; echo "shutdown in 2 min (the instance terminates; the volumes stay)"; shutdown -h +2
  fi
else
  { echo "x1k long rows ALERT $(date -u +%FT%TZ): all units inactive, clean=$clean (a unit without 'census finished' or a project without upload and not in excluded.tsv), size check ok=$ok; no shutdown"; } > $T/ALERT
  aws s3 cp $T/ALERT $B/dataset-x1k/live-a/ALERT --only-show-errors; cat $T/ALERT
fi
EOF_x1k_long_finalize
for f in x1k-long-run x1k-long-upload x1k-long-status x1k-long-live x1k-long-watch x1k-long-finalize; do
  chmod 755 /usr/local/bin/$f.new; mv -f /usr/local/bin/$f.new /usr/local/bin/$f; done
cat > /etc/systemd/system/x1k-long@.service <<'EOF_u1'
[Unit]
Description=x1k long row %i (one-project ctp run, full v1 pipeline, own tree /data/x1k-long/%i)
Wants=network-online.target
After=network-online.target nix-daemon.service
RequiresMountsFor=/data1 /data2 /data3 /data4
OnSuccess=x1k-long-finalize.service
OnFailure=x1k-long-finalize.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/data/x1k-long/%i/ctp
ExecStart=/usr/local/bin/x1k-long-run %i
StandardOutput=append:/data/x1k-long/%i/logs/run.log
StandardError=append:/data/x1k-long/%i/logs/run.log
Restart=no
KillMode=mixed
TimeoutStopSec=60
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
EOF_u1
cat > /etc/systemd/system/x1k-long-finalize.service <<'EOF_u2'
[Unit]
Description=x1k long rows: final copy to S3 and power-off when every unit has ended

[Service]
Type=oneshot
ExecStart=/usr/local/bin/x1k-long-finalize
StandardOutput=append:/data/logs/x1k-long-finalize.log
StandardError=append:/data/logs/x1k-long-finalize.log
TimeoutStartSec=3600
EOF_u2
cat > /etc/systemd/system/x1k-long-finalize.timer <<'EOF_u3'
[Unit]
Description=x1k long rows: finalize check every 15 min

[Timer]
OnActiveSec=15min
OnUnitActiveSec=15min
EOF_u3
cat > /etc/systemd/system/x1k-long-upload.service <<'EOF_u4'
[Unit]
Description=x1k long rows: copy finished projects to S3 dataset-x1k/done-full/

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/x1k-long-upload
StandardOutput=append:/data/logs/x1k-long-upload.log
StandardError=append:/data/logs/x1k-long-upload.log
TimeoutStartSec=3600
EOF_u4
cat > /etc/systemd/system/x1k-long-upload.timer <<'EOF_u5'
[Unit]
Description=x1k long rows: copy finished projects to S3 every 2 min

[Timer]
OnActiveSec=2min
OnUnitActiveSec=2min
AccuracySec=10s
EOF_u5
cat > /etc/systemd/system/x1k-long-live.service <<'EOF_u6'
[Unit]
Description=x1k long rows: live status to S3

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/x1k-long-live
TimeoutStartSec=600
EOF_u6
cat > /etc/systemd/system/x1k-long-live.timer <<'EOF_u7'
[Unit]
Description=x1k long rows: live status to S3 every 10 min

[Timer]
OnActiveSec=1min
OnUnitActiveSec=10min
AccuracySec=30s
EOF_u7
cat > /etc/systemd/system/x1k-long-watch.service <<'EOF_u8'
[Unit]
Description=x1k long rows: watch for a spot interruption notice (IMDSv2)
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/x1k-long-watch
StandardOutput=append:/data/logs/x1k-long-watch.log
StandardError=append:/data/logs/x1k-long-watch.log
Restart=always
RestartSec=5
EOF_u8
mkdir -p /data/logs; chown ec2-user: /data/logs
systemctl daemon-reload
for f in x1k-long-run x1k-long-status x1k-long-live x1k-long-watch x1k-long-finalize; do bash -n /usr/local/bin/$f; done
python3 -c 'import ast, sys; ast.parse(open(sys.argv[1]).read())' /usr/local/bin/x1k-long-upload
echo "R3 (machine A) installed: $(ls /usr/local/bin | grep -c '^x1k-long-') scripts, units: $(ls /etc/systemd/system | grep '^x1k-long' | tr '\n' ' ')"
