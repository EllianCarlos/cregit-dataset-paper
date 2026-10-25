#!/usr/bin/env bash
# R3-install-b.sh (machine B of the x1k relaunch, FULL pipeline; copy of R3-install.sh with a run
# id). User decision 2026-10-19: the x1k rows join the released dataset, so B runs the v1 code path:
# the UNPATCHED ctp ca113e3 (no ctp-no-firm.patch, no --no-firm: the firm step, the join and the
# full validate run), cregit 57551d7, and the flags of the v1 fed parts (census-fed-run of
# ec2-batch6/scripts/s6-files-0.sh): --retries 3 --skip-html --latest --tokenizer-worker
# --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300. R2 checks this path
# (libexpat full steps = 14eb5d72, the gate of the v1 batches 7-26).
# Run it through scripts/w6/ssm-run.sh, which gives X1K_RUN (the NAME of the L1-launch-b.sh
# instance: dataset-x1k-b<slot>, after a reclaim dataset-x1k-b<slot>-r<n>; slot 1 or 2). The run id
# goes to /etc/dataset-x1k/run, the slot to /etc/dataset-x1k/slot (R4-start-b.sh: slot 1 runs
# parts 1-4 of the deal, slot 2 parts 5-8). The live and final files go to
# s3://B/dataset-x1k/live/<run>/ and final/<run>/, so a relaunch never writes over the files of an
# earlier run (live/ of the first run stays as it is). The done set of the full run is
# s3://B/dataset-x1k/done-full/<name>/ (the old done/ of the --no-firm run stays untouched; its
# Parquets have no firm columns). x1k-upload does not write into a done-full/<name>/ that has an
# OK. x1k-finalize powers off only after final/<run>/DONE is in S3 with the correct size.
# The text below is from R3 (where it says --no-firm or done/, B uses the above):
# R3-install.sh (the x1k instance, root, through ssm.sh; idempotent; starts nothing): the run
# scripts and units of the x1k test run, made from the v1 spot-part tools (census-fed-run,
# census-fed-upload, census-fed-live, census-fed-watch, census-fed-finalize):
#   x1k@K.service      ctp census of part pK (ca113e3 + ctp-no-firm.patch, --no-firm), flags of the
#                      v1 fed parts; OOMPolicy=continue; OnSuccess/OnFailure -> x1k-finalize;
#   x1k-upload.timer   every 2 min: each finished project (final ledger row done/done-dirty and
#                      its .validated stamp) to s3://B/dataset-x1k/done/<name>/ with a size check
#                      and an OK file (Parquet sha256), as census-fed-upload;
#   x1k-live.timer     every 10 min: s3://B/dataset-x1k/live/<run>/progress.txt;
#   x1k-watch.service  spot notice (IMDSv2) -> STOP in every part, INTERRUPTED, one upload;
#   x1k-finalize       after every part ends (and every 15 min): copy ledgers and logs to
#                      s3://B/dataset-x1k/final/<run>/pK/, check sizes, write final/<run>/DONE; then, if every
#                      part ended with "census finished", no /home/ec2-user/NO_SHUTDOWN and no
#                      /run/x1k-hold, and the machine is up >= 1 h: shutdown -h (it terminates).
#                      A part that ended without "census finished" -> live/<run>/ALERT, no shutdown.
set -euo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_A}) echo "ABORT: $IID is on the refuse list"; exit 1 ;; esac
RUN=${X1K_RUN:-}
[[ $RUN =~ ^dataset-x1k-b([12])(-r[0-9]+)?$ ]] || { echo "ABORT: X1K_RUN '$RUN' is not dataset-x1k-b1|b2[-rN]; run R3-install-b.sh through scripts/w6/ssm-run.sh"; exit 1; }
SLOT=${BASH_REMATCH[1]}
mkdir -p /etc/dataset-x1k
if [ -f /etc/dataset-x1k/run ] && [ "$(cat /etc/dataset-x1k/run)" != "$RUN" ]; then
  echo "ABORT: this instance has the run id $(cat /etc/dataset-x1k/run), not $RUN"; exit 1
fi
echo "$RUN" > /etc/dataset-x1k/run; echo "$SLOT" > /etc/dataset-x1k/slot; chmod 644 /etc/dataset-x1k/run /etc/dataset-x1k/slot
echo "run id $RUN, slot $SLOT: live files to dataset-x1k/live/$RUN/, final files to dataset-x1k/final/$RUN/, done set dataset-x1k/done-full/"
cat > /usr/local/bin/x1k-run.new <<'EOF_x1k_run'
#!/usr/bin/env bash
# x1k-run K (x1k@K.service, ec2-user): the ctp census of x1k part pK. Stop after the running
# projects: touch /dataK/x1k/ctp/STOP (x1k-watch does it on a spot notice).
set -euo pipefail
K=${1:?part}; P=/data$K/x1k; I=/data/x1k-inputs; M=$P/manifest.run.tsv
W=$(cat /etc/dataset-x1k/workers 2>/dev/null || echo 6)
export CTP_CONFIG=/etc/dataset-x1k/p$K.cfg
cd $P/ctp
# the v1 code path: ctp ca113e3 without any patch
[ ! -e .x1k-patched ] && [ "$(git rev-parse --short HEAD)" = ca113e3 ] && [ -z "$(git status --porcelain --untracked-files=no)" ] \
  || { echo "ctp of p$K is not the clean ca113e3 (patched or changed)"; exit 2; }
echo "=== $(date -u +%FT%TZ) x1k part p$K start on $(cat /sys/devices/virtual/dmi/id/board_asset_tag) run $(cat /etc/dataset-x1k/run) (cregit $(git -C $P/cregit-ec2 rev-parse --short HEAD), ctp $(git rev-parse --short HEAD) full pipeline, $(grep -c -v -e '^#' -e '^[[:space:]]*$' $M) projects, $W workers)"
exec .venv/bin/python ctp.py census --manifest "$M" --project-meta "$I/project_meta.x1k.json" \
    --workers "$W" --retries 3 --skip-html --latest --tokenizer-worker \
    --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300
EOF_x1k_run
cat > /usr/local/bin/x1k-upload.new <<'EOF_x1k_upload'
#!/usr/bin/env python3
"""x1k-upload (x1k-upload.timer, ec2-user): copy each finished x1k project to S3.

Made from census-fed-upload of the v1 spot parts. A project is finished when its last final ledger
row ("project") says done or done-dirty and its .validated stamp exists. For each one not yet
uploaded it copies out/<name>/<name>-dataset.parquet, out/<name>/<name>.validated,
out/<name>/<name>-persons.db (if it exists), ctp state/<name>/*.json and state/<name>/logs/*
(regular files) and the ledger rows of the project (ledger.rows.jsonl; not the whole part ledger)
to s3://BUCKET/dataset-x1k/done-full/<name>/ (machine B), lists the prefix back and compares every key and size,
then writes done-full/<name>/OK (time, instance, part, files, sizes, Parquet sha256) and a local
marker /dataK/x1k/uploaded/<name>. A restart leaves out exactly the projects that have OK.
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

B = "s3://${RUNNER_BUCKET}"
DEST = f"{B}/dataset-x1k/done-full"  # B full run: own done set; done/ (the --no-firm run) stays untouched


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


def upload(name, k, part, rows):
    ctp, out = part / "ctp", part / "out"
    pq = out / name / f"{name}-dataset.parquet"
    stamp = out / name / f"{name}.validated"
    if not (pq.is_file() and stamp.is_file()):
        return f"p{k} {name}: Parquet or stamp missing, later"
    have = subprocess.run(["aws", "s3", "ls", f"{DEST}/{name}/OK"], capture_output=True, text=True)
    if have.returncode == 0 and have.stdout.strip().endswith(" OK"):
        (part / "uploaded").mkdir(parents=True, exist_ok=True)
        (part / "uploaded" / name).write_text("done-full/OK was in S3 before this run; nothing uploaded\n")
        return f"p{k} {name}: done-full/{name}/OK exists already, not overwritten"
    stage = part / "upload-stage"  # same filesystem as out/, so os.link works
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
            return f"p{k} {name}: size check FAILED for {bad[:5]}, will retry"
        ok = tmp / "OK"
        instance = Path("/sys/devices/virtual/dmi/id/board_asset_tag").read_text().strip()
        ok.write_text(f"uploaded {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} from {instance} part p{k}\n"
                      f"parquet_sha256 {sha256(pq)}\n"
                      + "".join(f"{v}\t{key}\n" for key, v in sorted(local.items())))
        subprocess.run(["aws", "s3", "cp", str(ok), f"{DEST}/{name}/OK", "--only-show-errors"], check=True)
        (part / "uploaded").mkdir(parents=True, exist_ok=True)
        (part / "uploaded" / name).write_text(ok.read_text())
        return f"p{k} {name}: uploaded {len(local)} files, sizes equal, OK written"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for k in (1, 2, 3, 4):
        part = Path(f"/data{k}/x1k")
        names, rows = finished(part / "ctp")
        for name in names:
            if (part / "uploaded" / name).exists():
                continue
            try:
                print(time.strftime("%FT%TZ", time.gmtime()), upload(name, k, part, rows), flush=True)
            except (subprocess.CalledProcessError, OSError) as x:
                print(time.strftime("%FT%TZ", time.gmtime()), f"p{k} {name}: upload error {x}, will retry", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
EOF_x1k_upload
cat > /usr/local/bin/x1k-live.new <<'EOF_x1k_live'
#!/usr/bin/env bash
# x1k-live (x1k-live.timer, ec2-user): the run state to s3://B/dataset-x1k/live/<run>/progress.txt.
set -uo pipefail
B=s3://${RUNNER_BUCKET}
RUN=$(cat /etc/dataset-x1k/run)
T=$(mktemp)
{
  echo "x1k live run $RUN $(date -u +%FT%TZ) on $(cat /sys/devices/virtual/dmi/id/board_asset_tag), up $(awk '{printf "%.1f h", $1/3600}' /proc/uptime)"
  tot=0; done_=0
  for K in 1 2 3 4; do P=/data$K/x1k; M=$P/manifest.run.tsv
    n=$(grep -c -v -e '^#' -e '^[[:space:]]*$' $M 2>/dev/null); n=${n:-0}; u=$(ls $P/uploaded 2>/dev/null | wc -l)
    tot=$((tot + n)); done_=$((done_ + u))
    echo "--- p$K: unit $(systemctl is-active x1k@$K) | uploaded $u of $n | $(df -h --output=avail /data$K | tail -1 | tr -d ' ') free"
    (cd $P/ctp && CTP_CONFIG=/etc/dataset-x1k/p$K.cfg .venv/bin/python ctp.py progress --manifest $M --last 2 2>&1 | head -6)
    tail -1 $P/logs/run.log 2>/dev/null | cut -c1-200
  done
  echo "=== all parts: uploaded $done_ of $tot"
  free -g | sed -n 2p; uptime
  [ -e /run/x1k-spot-interrupted ] && echo "SPOT INTERRUPTION: $(cat /run/x1k-spot-interrupted)"
} > $T 2>&1
aws s3 cp $T $B/dataset-x1k/live/$RUN/progress.txt --only-show-errors
rm -f $T
EOF_x1k_live
cat > /usr/local/bin/x1k-watch.new <<'EOF_x1k_watch'
#!/usr/bin/env bash
# x1k-watch (x1k-watch.service, root): poll IMDSv2 spot/instance-action every 5 s, as census-fed-watch.
# On a notice: /run/x1k-spot-interrupted, STOP in every part's ctp clone (no new project starts),
# INTERRUPTED and each part's ledger to s3://B/dataset-x1k/live/<run>/, one x1k-upload. EC2 terminates the
# instance about 2 min later; the relaunch steps are in ~/s3-work/dataset-x1k/README.md.
set -uo pipefail
B=s3://${RUNNER_BUCKET}
IMDS=http://169.254.169.254/latest
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
RUN=$(cat /etc/dataset-x1k/run)
echo "$(date -u +%FT%TZ) watching $IMDS/meta-data/spot/instance-action every 5 s"
while :; do
  tok=$(curl -s -m 2 -X PUT "$IMDS/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
  if [ -n "$tok" ]; then
    code=$(curl -s -m 2 -o /run/x1k-instance-action -w '%{http_code}' -H "X-aws-ec2-metadata-token: $tok" "$IMDS/meta-data/spot/instance-action")
    if [ "$code" = 200 ]; then
      echo "$(date -u +%FT%TZ) $(cat /run/x1k-instance-action)" > /run/x1k-spot-interrupted
      T=$(mktemp -d)
      for K in 1 2 3 4; do touch /data$K/x1k/ctp/STOP; chown ec2-user: /data$K/x1k/ctp/STOP
        [ -f /data$K/x1k/ctp/ledger.jsonl ] && cp /data$K/x1k/ctp/ledger.jsonl $T/ledger.p$K.jsonl; done
      { echo "spot interruption notice seen $(date -u +%FT%TZ) on $IID (run $RUN)"; cat /run/x1k-instance-action; echo
        for K in 1 2 3 4; do echo "p$K uploaded $(ls /data$K/x1k/uploaded | wc -l)"; done; } > $T/INTERRUPTED
      aws s3 cp $T/ $B/dataset-x1k/live/$RUN/ --recursive --only-show-errors
      sudo -u ec2-user /usr/local/bin/x1k-upload
      echo "real notice handled; idle until termination"; exec sleep infinity
    fi
  fi
  sleep 5
done
EOF_x1k_watch
cat > /usr/local/bin/x1k-finalize.new <<'EOF_x1k_finalize'
#!/usr/bin/env bash
# x1k-finalize (root; x1k-finalize.service, after each part ends and every 15 min): see R3-install.sh.
set -uo pipefail
B=s3://${RUNNER_BUCKET}
E=/etc/dataset-x1k
[ -f $E/started ] || exit 0
RUN=$(cat $E/run) || exit 1
F=$B/dataset-x1k/final/$RUN
[ -e /run/x1k-spot-interrupted ] && exit 0
for K in 1 2 3 4; do systemctl is-active -q x1k@$K && exit 0; done
[ -f $E/final-DONE ] && exit 0
echo "$(date -u +%FT%TZ) all 4 parts inactive: final upload"
sudo -u ec2-user /usr/local/bin/x1k-upload
clean=1; T=$(mktemp -d)
for K in 1 2 3 4; do P=/data$K/x1k; C=$P/ctp; mkdir -p $T/p$K
  grep -q 'census finished rc=' $P/logs/run.log 2>/dev/null || clean=0
  for f in ledger.jsonl runs.log metrics.tsv resources.tsv; do [ -f $C/$f ] && cp $C/$f $T/p$K/; done
  cp $P/logs/run.log $P/manifest.run.tsv $T/p$K/ 2>/dev/null
  ls $P/uploaded > $T/p$K/uploaded.txt
  # state of the projects without an upload (failed, deferred or not started)
  (cd $C/state 2>/dev/null && ls | grep -v -x -F -f $T/p$K/uploaded.txt | tar -czf $T/p$K/state-not-uploaded.tar.gz -T - 2>/dev/null)
done
aws s3 cp $T/ $F/ --recursive --only-show-errors
ok=1
for f in $(cd $T && find . -type f | sed 's|^\./||'); do
  s=$(aws s3 ls $F/$f | awk '{print $3}')
  [ "$s" = "$(stat -c %s $T/$f)" ] || { ok=0; echo "size check failed: $f"; }
done
if [ $ok = 1 ] && [ $clean = 1 ]; then
  { echo "x1k final run $RUN $(date -u +%FT%TZ) on $(cat /sys/devices/virtual/dmi/id/board_asset_tag)"
    for K in 1 2 3 4; do echo "p$K: uploaded $(wc -l < $T/p$K/uploaded.txt) of $(grep -c -v -e '^#' -e '^[[:space:]]*$' $T/p$K/manifest.run.tsv); $(grep 'census finished rc=' $T/p$K/run.log | tail -1 | cut -c1-200)"; done
  } > $T/DONE
  aws s3 cp $T/DONE $F/DONE --only-show-errors
  cat $T/DONE
  up=$(awk '{print int($1)}' /proc/uptime)
  # Power off only when final/<run>/DONE is in S3 with the local size; else no final-DONE, so the
  # next timer run (15 min) does the final copy again.
  if [ "$(aws s3 ls $F/DONE | awk '{print $3}')" != "$(stat -c %s $T/DONE)" ]; then
    echo "final/$RUN/DONE is not in S3 with the correct size: no shutdown, retry at the next timer run"
  elif ! cp $T/DONE $E/final-DONE; then
    echo "cannot write $E/final-DONE: no shutdown"
  elif [ -e /home/ec2-user/NO_SHUTDOWN ] || [ -e /run/x1k-hold ] || [ "$up" -lt 3600 ]; then
    echo "no shutdown (NO_SHUTDOWN, /run/x1k-hold or up < 1 h)"
  else
    echo "shutdown in 2 min (the instance terminates)"; shutdown -h +2
  fi
else
  { echo "x1k ALERT run $RUN $(date -u +%FT%TZ): all parts inactive, clean=$clean (a part without 'census finished'), size check ok=$ok; no shutdown"; } > $T/ALERT
  aws s3 cp $T/ALERT $B/dataset-x1k/live/$RUN/ALERT --only-show-errors; cat $T/ALERT
fi
EOF_x1k_finalize
for f in x1k-run x1k-upload x1k-live x1k-watch x1k-finalize; do chmod 755 /usr/local/bin/$f.new; mv -f /usr/local/bin/$f.new /usr/local/bin/$f; done
cat > /etc/systemd/system/x1k@.service <<'EOF_u1'
[Unit]
Description=x1k machine B part p%i (ctp census, full pipeline, own XFS /data%i)
Wants=network-online.target
After=network-online.target nix-daemon.service
RequiresMountsFor=/data%i
OnSuccess=x1k-finalize.service
OnFailure=x1k-finalize.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/data%i/x1k/ctp
ExecStart=/usr/local/bin/x1k-run %i
StandardOutput=append:/data%i/x1k/logs/run.log
StandardError=append:/data%i/x1k/logs/run.log
Restart=no
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStopSec=300
EOF_u1
cat > /etc/systemd/system/x1k-finalize.service <<'EOF_u2'
[Unit]
Description=x1k test run: final copy to S3 and power-off when every part has ended

[Service]
Type=oneshot
ExecStart=/usr/local/bin/x1k-finalize
StandardOutput=append:/data/logs/x1k-finalize.log
StandardError=append:/data/logs/x1k-finalize.log
TimeoutStartSec=3600
EOF_u2
cat > /etc/systemd/system/x1k-finalize.timer <<'EOF_u3'
[Unit]
Description=x1k test run: finalize check every 15 min

[Timer]
OnActiveSec=15min
OnUnitActiveSec=15min
EOF_u3
cat > /etc/systemd/system/x1k-upload.service <<'EOF_u4'
[Unit]
Description=x1k machine B: copy finished projects to S3 dataset-x1k/done-full/

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/x1k-upload
StandardOutput=append:/data/logs/x1k-upload.log
StandardError=append:/data/logs/x1k-upload.log
TimeoutStartSec=3600
EOF_u4
cat > /etc/systemd/system/x1k-upload.timer <<'EOF_u5'
[Unit]
Description=x1k test run: copy finished projects to S3 every 2 min

[Timer]
OnActiveSec=2min
OnUnitActiveSec=2min
AccuracySec=10s
EOF_u5
cat > /etc/systemd/system/x1k-live.service <<'EOF_u6'
[Unit]
Description=x1k test run: live status to S3

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/x1k-live
TimeoutStartSec=600
EOF_u6
cat > /etc/systemd/system/x1k-live.timer <<'EOF_u7'
[Unit]
Description=x1k test run: live status to S3 every 10 min

[Timer]
OnActiveSec=1min
OnUnitActiveSec=10min
AccuracySec=30s
EOF_u7
cat > /etc/systemd/system/x1k-watch.service <<'EOF_u8'
[Unit]
Description=x1k test run: watch for a spot interruption notice (IMDSv2)
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/x1k-watch
StandardOutput=append:/data/logs/x1k-watch.log
StandardError=append:/data/logs/x1k-watch.log
Restart=always
RestartSec=5
EOF_u8
mkdir -p /data/logs; chown ec2-user: /data/logs
systemctl daemon-reload
bash -n /usr/local/bin/x1k-run && bash -n /usr/local/bin/x1k-live && bash -n /usr/local/bin/x1k-watch && bash -n /usr/local/bin/x1k-finalize \
  && python3 -c 'import ast, sys; ast.parse(open(sys.argv[1]).read())' /usr/local/bin/x1k-upload && echo "R3-b installed (run $RUN): $(ls /usr/local/bin | grep -c '^x1k-') scripts, units: $(ls /etc/systemd/system | grep '^x1k' | tr '\n' ' ')"
