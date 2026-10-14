set -euo pipefail
cat > /usr/local/bin/census-batch4-guard.new <<'EOF_census-batch4-guard'
#!/usr/bin/env bash
# census-batch4-guard (root, every 10 min). The loop images /data/loop/b4pK.img are sparse files on
# the RAID0 /data that batch 2 and batch 3L also use. (1) fstrim each /b4pK, so blocks freed inside
# (cleaned-up clones) are punched out of the image and returned to /data (measured 13:12: the
# discard mount option alone did not shrink the image, fstrim did). (2) If /data has less than
# GUARD_GB (default 800) GiB free, touch STOP in every batch 4 ctp clone: running batch 4 projects
# finish, no new one starts, so batch 4 cannot fill /data under batch 2 / batch 3L.
set -uo pipefail
export AWS_PAGER=""
G=${GUARD_GB:-800}
for k in 1 2 3; do mountpoint -q /b4p$k && fstrim /b4p$k >/dev/null; done
avail=$(df -BG --output=avail /data | tail -1 | tr -dc 0-9)
img=$(for k in 1 2 3; do echo -n "b4p$k $(du -BG /data/loop/b4p$k.img | cut -f1) "; done)
msg="$(date -u +%FT%TZ) /data free ${avail}G (guard ${G}G); image use: $img"
if [ "$avail" -lt "$G" ]; then
  for k in 1 2 3; do [ -d /b4p$k/ctp ] && { touch /b4p$k/ctp/STOP; chown ec2-user: /b4p$k/ctp/STOP; }; done
  msg="$msg; BELOW GUARD: STOP written in /b4p1..3/ctp"
  echo "$msg" > /run/census-batch4-guard.tripped
  aws s3 cp /run/census-batch4-guard.tripped s3://${RUNNER_BUCKET}/batch4/live/GUARD --only-show-errors
fi
echo "$msg" > /run/census-batch4-guard.status
echo "$msg"
EOF_census-batch4-guard
chmod 755 /usr/local/bin/census-batch4-guard.new
mv -f /usr/local/bin/census-batch4-guard.new /usr/local/bin/census-batch4-guard
set +e
export AWS_PAGER=""
B=/usr/local/bin
$B/census-batch4-guard
for k in 1 2 3; do [ -e /b4p$k/ctp/STOP ] && { echo "STOP in /b4p$k/ctp: not starting"; exit 1; }; done
systemctl is-active --quiet census-batch2.service && systemctl is-active --quiet census-batch3L.service || echo "note: batch2/3L state changed"
systemctl enable --now census-batch4-guard.timer census-batch4-live.timer 2>&1 | tail -2
for k in 1 2 3; do systemctl start census-batch4p$k.service; echo "started census-batch4p$k at $(date -u +%FT%TZ)"; done
sleep 60
systemctl is-active census-batch4p1.service census-batch4p2.service census-batch4p3.service census-batch4-live.timer census-batch4-guard.timer census-batch2.service census-batch3L.service | tr '\n' ' '; echo
for k in 1 2 3; do tail -n 2 /data/logs/batch4p$k.log | cut -c1-200; done
sudo -u ec2-user $B/census-batch4-live; aws s3 cp s3://${RUNNER_BUCKET}/batch4/live/progress.txt - | head -2
systemctl list-timers 'census*' --no-pager | head -8
