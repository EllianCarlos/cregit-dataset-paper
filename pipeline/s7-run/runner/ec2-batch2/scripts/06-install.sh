set -euo pipefail
cat > /usr/local/bin/census-batch2-run <<'EOF_census-batch2-run'
#!/usr/bin/env bash
# Census batch 2 (EC2 m6id.24xlarge). Mirrors s7-run/run_batch1.sh, with the batch 2
# manifest in its u order, cregit 95cdc88 at /data/cregit-ec2, output on the RAID0.
# Stop after the running projects: touch /home/ec2-user/ctp/STOP. Resume: start the unit again.
set -euo pipefail
I=/home/ec2-user/batch2-input
export CTP_CONFIG=/home/ec2-user/census-batch2.cfg
cd /home/ec2-user/ctp
echo "=== $(date -u +%FT%TZ) census-batch2 start (cregit $(git -C /data/cregit-ec2 rev-parse --short HEAD), ctp $(git rev-parse --short HEAD))"
exec .venv/bin/python ctp.py census --manifest "$I/manifest.batch2.tsv" \
    --project-meta "$I/project_meta.batch2.json" \
    --workers 20 --retries 3 --skip-html --latest --tokenizer-worker \
    --blame-jobs 4 --memory-limit 8GB --min-free-mem-gb 24 --disk-floor-gb 500
EOF_census-batch2-run
chmod 755 /usr/local/bin/census-batch2-run
cat > /usr/local/bin/census-batch2-live <<'EOF_census-batch2-live'
#!/usr/bin/env bash
# Every 10 min (census-batch2-live.timer): status of the census to s3://BUCKET/batch2/live/.
set -uo pipefail
D=s3://${RUNNER_BUCKET}/batch2/live
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
export CTP_CONFIG=/home/ec2-user/census-batch2.cfg
{ echo "as of $(date -u +%FT%TZ)  census-batch2: $(systemctl is-active census-batch2.service) ($(systemctl show census-batch2.service -p Result --value))"
  echo "uptime: $(uptime)"
  echo "MemAvailable: $(awk '/MemAvailable/{printf "%.1f GiB", $2/1048576}' /proc/meminfo)   /data free: $(df -BG --output=avail /data | tail -1 | tr -d ' ')"
  echo
  cd /home/ec2-user/ctp && .venv/bin/python ctp.py progress --manifest /home/ec2-user/batch2-input/manifest.batch2.tsv --last 10 2>&1
} > "$T/progress.txt"
tail -n 300 /data/logs/batch2.log > "$T/batch2.log.tail" 2>/dev/null || true
{ date -u +%FT%TZ; uptime; cat /proc/meminfo; df -h /data /; } > "$T/system.txt"
[ -f /home/ec2-user/ctp/ledger.jsonl ] && cp /home/ec2-user/ctp/ledger.jsonl "$T/ledger.jsonl"
aws s3 cp "$T/" "$D/" --recursive --only-show-errors
EOF_census-batch2-live
chmod 755 /usr/local/bin/census-batch2-live
cat > /usr/local/bin/census-batch2-finalize <<'EOF_census-batch2-finalize'
#!/usr/bin/env bash
# Runs when census-batch2.service exits (OnSuccess=/OnFailure=). Copies the results to
# s3://BUCKET/batch2/final/, checks every object (key and size) and SHA256SUMS against the
# local files, writes DONE, then powers off (the instance STOPS; the RAID0 is lost).
# No power-off if the check fails, with --dry-run, if the census ran < 1 h, or if
# /home/ec2-user/NO_SHUTDOWN exists.
# --dry-run: copy to batch2/dryrun/ from CTP/OUT given in the environment, never power off.
set -uo pipefail
DRY=0; [ "${1:-}" = --dry-run ] && DRY=1
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
if [ $DRY = 1 ]; then say "dry run: no power-off"; exit 0; fi
st=$(systemctl show census-batch2.service -p ExecMainStartTimestampMonotonic --value); ex=$(systemctl show census-batch2.service -p ExecMainExitTimestampMonotonic --value)
ran=$(( (${ex:-0} - ${st:-0}) / 1000000 ))
if [ "$ran" -lt 3600 ]; then say "the census ran only ${ran}s (< 1 h): an early failure, so no power-off; look at $CLOG"; exit 0; fi
if [ -e /home/ec2-user/NO_SHUTDOWN ]; then say "/home/ec2-user/NO_SHUTDOWN exists: no power-off"; exit 0; fi
say "powering off (the instance stops; it is not terminated)"
sync; shutdown -h now
EOF_census-batch2-finalize
chmod 755 /usr/local/bin/census-batch2-finalize
cat > /etc/systemd/system/census-batch2.service <<'EOF_UNIT'
[Unit]
Description=cregit census batch 2 (ctp census, 20 workers)
Wants=network-online.target
After=network-online.target nix-daemon.service
RequiresMountsFor=/data
OnSuccess=census-batch2-finalize.service
OnFailure=census-batch2-finalize.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/home/ec2-user/ctp
ExecStart=/usr/local/bin/census-batch2-run
StandardOutput=append:/data/logs/batch2.log
StandardError=append:/data/logs/batch2.log
Restart=no
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStopSec=300
EOF_UNIT
cat > /etc/systemd/system/census-batch2-finalize.service <<'EOF_UNIT'
[Unit]
Description=cregit census batch 2: copy results to S3, write DONE, power off
RequiresMountsFor=/data

[Service]
Type=oneshot
ExecStart=/usr/local/bin/census-batch2-finalize
TimeoutStartSec=infinity
EOF_UNIT
cat > /etc/systemd/system/census-batch2-live.service <<'EOF_UNIT'
[Unit]
Description=cregit census batch 2: live status to S3

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/census-batch2-live
TimeoutStartSec=300
EOF_UNIT
cat > /etc/systemd/system/census-batch2-live.timer <<'EOF_UNIT'
[Unit]
Description=cregit census batch 2: live status to S3 every 10 min

[Timer]
OnActiveSec=1min
OnUnitActiveSec=10min
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF_UNIT
cat > /home/ec2-user/census-batch2.cfg <<'C'
# ctp config (CTP_CONFIG) for census batch 2 on EC2: cregit 95cdc88, output on the RAID0.
[paths]
cregit_dir = /data/cregit-ec2
output_dir = /data/census-2026-10-batch2
C
chown ec2-user: /home/ec2-user/census-batch2.cfg
mkdir -p /data/census-2026-10-batch2 /data/logs && chown ec2-user: /data/census-2026-10-batch2 /data/logs
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/census-batch2*.service /etc/systemd/system/census-batch2-live.timer 2>&1 | grep -v -e 'Unknown key' || true
echo installed
