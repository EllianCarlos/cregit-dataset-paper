mkdir -p /root/ssm
cat > /root/ssm/census-backup.payload <<'PAYLOAD_EOF'
#!/usr/bin/env bash
# census-backup (2026-10-09, user request: regular S3 backup of the Parquets). Every 30 min from
# census-backup.timer. For each finished project (a *.validated file next to its Parquet) that has no
# s3://BUCKET/<run>/done/<project>/OK yet: copy the Parquet, .validated and persons files, compare the
# S3 sizes with the local sizes, then write OK (with the Parquet sha256). Each pass also copies each
# run's ledger.jsonl, metrics.tsv and resources.tsv to <run>/backup-ledger/. Read-only on the census.
set -uo pipefail
exec 9>/run/census-backup.lock; flock -n 9 || exit 0
B=s3://${RUNNER_BUCKET}
log=/data/logs/census-backup.log
ts() { date -u +%FT%TZ; }
# run prefix | output dir | ctp dir
RUNS="batch2|/data/census-2026-10-batch2|/home/ec2-user/ctp
batch3L|/data/census-2026-10-batch3L|/home/ec2-user/ctp-b3L
batch4/p1|/b4p1/census-2026-10-batch4|/b4p1/ctp
batch4/p2|/b4p2/census-2026-10-batch4|/b4p2/ctp
batch4/p3|/b4p3/census-2026-10-batch4|/b4p3/ctp
batch5L|/b5L/census-2026-10-batch5L|/b5L/ctp"
done_list=$(mktemp); trap 'rm -f "$done_list"' EXIT
new=0; fail=0
while IFS='|' read -r run out ctp; do
  [ -d "$out" ] || continue
  aws s3 ls "$B/$run/done/" --recursive 2>/dev/null | awk '/\/OK$/{print $4}' > "$done_list"
  for v in "$out"/*/*.validated; do
    [ -e "$v" ] || continue
    d=$(dirname "$v"); p=$(basename "$d")
    case "$p" in .*) continue ;; esac
    grep -qx "$run/done/$p/OK" "$done_list" && continue
    pq="$d/$p-dataset.parquet"; [ -s "$pq" ] || { echo "$(ts) $run $p: no parquet yet" >> "$log"; continue; }
    ok=1
    for f in "$pq" "$v" "$d/$p-persons.db" "$d/$p-persons.xls"; do
      [ -e "$f" ] || continue
      key="$run/done/$p/$(basename "$f")"
      nice -n 10 aws s3 cp "$f" "$B/$key" --only-show-errors || { ok=0; break; }
      rs=$(aws s3api head-object --bucket "${B#s3://}" --key "$key" --query ContentLength --output text 2>/dev/null)
      [ "$rs" = "$(stat -c %s "$f")" ] || { ok=0; break; }
    done
    if [ $ok = 1 ]; then
      printf '%s  %s\nbacked_up=%s\n' "$(sha256sum "$pq" | cut -d' ' -f1)" "$(basename "$pq")" "$(ts)" \
        | aws s3 cp - "$B/$run/done/$p/OK" --only-show-errors && new=$((new + 1))
    else
      fail=$((fail + 1)); echo "$(ts) $run $p: upload or size check FAILED" >> "$log"
    fi
  done
  for f in ledger.jsonl metrics.tsv resources.tsv; do
    [ -e "$ctp/$f" ] && aws s3 cp "$ctp/$f" "$B/$run/backup-ledger/$f" --only-show-errors
  done
done <<<"$RUNS"
echo "$(ts) pass done: new=$new failed=$fail" >> "$log"
PAYLOAD_EOF
set -euo pipefail
install -m 0755 /root/ssm/census-backup.payload /usr/local/bin/census-backup
cat > /etc/systemd/system/census-backup.service <<'U'
[Unit]
Description=Back up finished census Parquets to S3 (read-only on the census)
[Service]
Type=oneshot
Nice=10
IOSchedulingClass=idle
ExecStart=/usr/local/bin/census-backup
U
cat > /etc/systemd/system/census-backup.timer <<'U'
[Unit]
Description=Back up finished census Parquets to S3 every 30 min
[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
[Install]
WantedBy=timers.target
U
for u in census-batch2 census-batch3L census-batch4p1 census-batch4p2 census-batch4p3 census-batch5L; do
  n=$(systemctl show -p NeedDaemonReload --value $u); echo "$u NeedDaemonReload=$n MainPID=$(systemctl show -p MainPID --value $u)"
  [ "$n" = no ] || { echo "ABORT: $u needs a daemon-reload; not reloading"; exit 3; }
done
systemctl daemon-reload
systemctl enable --now census-backup.timer
for u in census-batch2 census-batch3L census-batch4p1 census-batch4p2 census-batch4p3 census-batch5L; do
  echo "after $u MainPID=$(systemctl show -p MainPID --value $u) $(systemctl is-active $u)"
done
systemctl start census-backup.service; systemctl is-active census-backup.timer; tail -3 /data/logs/census-backup.log
