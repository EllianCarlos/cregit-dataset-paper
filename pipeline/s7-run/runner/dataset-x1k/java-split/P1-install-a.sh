#!/usr/bin/env bash
# P1-install-a.sh, machine A (root, through scripts/a/ssm-a.sh; after E1; made by render.sh from
# src/P1-install-a.body; idempotent). Installs the pull of the aws-sdk-java split:
#   /usr/local/lib/java-split/jv_pull.py, /usr/local/bin/jv-pull, /etc/java-split/pull.env,
#   jv-pull.service (oneshot, root) and jv-pull.timer (OnBootSec=5min, OnUnitActiveSec=10min).
# R8 (x1k-rebalance.timer) also runs every 10 min. They do not conflict: R8 only reads .blame
# counts and mtimes; the pulled files keep the mtime of the extra (the time it finished them),
# so R8's rate of the row counts them as the row's output, which is what the row's end time needs.
# A restart of the row by jv-pull takes R8's lock (rebalance.lock), so the two never restart at once.
# The rust-split kit can stay installed: its files are rs-pull.*, /usr/local/lib/rust-split,
# /etc/rust-split and /data/x1k-long/rust-split; this kit uses jv-pull.* and the java-split names.
# Each pull restarts only its own row, and both take rebalance.lock (flock -n) for a restart.
# Then it runs jv-pull once and prints its log block, and the timers of A.
# Env: AUTO_RESTART (1), STALE_MIN (40), RESTART_MIN (100).
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
[ "$IID" = ${RUNNER_EC2_X1K_LONG_A4} ] || { echo "ABORT: $IID is not machine A"; exit 1; }
S=/data/x1k-long/java-split
LIB=/usr/local/lib/java-split
AUTO_RESTART=${AUTO_RESTART:-1}; STALE_MIN=${STALE_MIN:-40}; RESTART_MIN=${RESTART_MIN:-100}
echo "== $(date -u +%FT%TZ) P1 install on $IID"
[ -s $S/e1/left.tsv ] && [ -s $S/e1/settings.env ] && [ -d $S/e1/parts ] || { echo "ABORT: run E1 first"; exit 1; }
N=$(sed -n 's/^N=//p' $S/e1/settings.env)
case $N in ''|*[!0-9]*) echo "ABORT: no N in e1/settings.env"; exit 1 ;; esac
mkdir -p $LIB /etc/java-split $S/state
chown ec2-user: $S $S/state
# embedded lib/jv_pull.py (sha256 2681a5efbce4d3ed)
mkdir -p "$(dirname "$LIB/jv_pull.py")"
base64 -d <<'EOF_JV_EMBED' | gunzip > "$LIB/jv_pull.py.tmp"
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
8P0uAAA=
EOF_JV_EMBED
[ "$(sha256sum < "$LIB/jv_pull.py.tmp" | cut -d" " -f1)" = 2681a5efbce4d3edb6ed44069a9fe55c25424d64c3d9037ca1e03b3a10082e06 ] || { echo "ABORT: embedded lib/jv_pull.py sha256"; exit 1; }
chmod 755 "$LIB/jv_pull.py.tmp" && mv -f "$LIB/jv_pull.py.tmp" "$LIB/jv_pull.py"
# embedded lib/jv-pull.sh (sha256 accfe4eab2dfcaa1)
mkdir -p "$(dirname "/usr/local/bin/jv-pull")"
base64 -d <<'EOF_JV_EMBED' | gunzip > "/usr/local/bin/jv-pull.tmp"
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
rrA9Sqz9F9IsT+EwJQAA
EOF_JV_EMBED
[ "$(sha256sum < "/usr/local/bin/jv-pull.tmp" | cut -d" " -f1)" = accfe4eab2dfcaa11dd8b121b1bb7c8ff49391d30017c72c126eeed8e6fe48c6 ] || { echo "ABORT: embedded lib/jv-pull.sh sha256"; exit 1; }
chmod 755 "/usr/local/bin/jv-pull.tmp" && mv -f "/usr/local/bin/jv-pull.tmp" "/usr/local/bin/jv-pull"
mkdir -p $S/state/pull $S/state/status; chown -R ec2-user: $S/state/pull
printf 'N=%s\nAUTO_RESTART=%s\nSTALE_MIN=%s\nRESTART_MIN=%s\n' "$N" "$AUTO_RESTART" "$STALE_MIN" "$RESTART_MIN" > /etc/java-split/pull.env
cat > /etc/systemd/system/jv-pull.service <<'EOF_s'
[Unit]
Description=java-split pull of aws-sdk-java .blame batches from the extra machines
Wants=network-online.target
After=network-online.target
RequiresMountsFor=/data1 /data3
[Service]
Type=oneshot
ExecStart=/usr/local/bin/jv-pull
TimeoutStartSec=3000
EOF_s
cat > /etc/systemd/system/jv-pull.timer <<'EOF_t'
[Unit]
Description=java-split pull every 10 min
[Timer]
OnBootSec=5min
OnUnitActiveSec=10min
[Install]
WantedBy=timers.target
EOF_t
systemctl daemon-reload
systemctl enable --now jv-pull.timer >/dev/null 2>&1
systemctl start jv-pull.service
echo "pull.env: $(tr '\n' ' ' < /etc/java-split/pull.env)"
echo "timer: $(systemctl is-active jv-pull.timer); next: $(systemctl list-timers jv-pull.timer --no-legend --no-pager | awk '{print $1, $2, $3}')"
n=$(grep -n '^== .* jv-pull on' $S/state/pull.log | tail -1 | cut -d: -f1)
[ -n "$n" ] && tail -n +"$n" $S/state/pull.log | head -30 | sed 's/@//g'
echo "timers on A:"; systemctl list-timers jv-pull.timer rs-pull.timer x1k-rebalance.timer --all --no-legend --no-pager | sed 's/^/  /'
echo "P1 install done $(date -u +%FT%TZ)"
