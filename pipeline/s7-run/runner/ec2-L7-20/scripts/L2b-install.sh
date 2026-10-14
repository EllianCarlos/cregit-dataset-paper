set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin; S3=s3://${RUNNER_BUCKET}
U=$(systemctl list-units --no-legend --plain --all 'census*' | awk '{print $1}')
for u in $U; do [ "$(systemctl show $u -p NeedDaemonReload --value)" = no ] || { echo "$u: NeedDaemonReload=yes; aborting"; exit 1; }; done
echo "NeedDaemonReload=no for all $(echo $U | wc -w) loaded census units"
R=$(systemctl list-units --no-legend --plain --state=active 'census*.service' | awk '{print $1}')
before=$(for u in $R; do echo "$u $(systemctl show $u -p MainPID -p ActiveEnterTimestamp --value | tr '\n' ' ')"; done)
cat > /etc/systemd/system/census-L7-20.service.new <<'EOF_census-L7-20.service'
[Unit]
Description=cregit census L7-20: the 55 L projects of batches 7-20, 6 workers (ctp census, loop XFS /bL7)
Wants=network-online.target
After=network-online.target nix-daemon.service
RequiresMountsFor=/data /bL7
OnSuccess=census-L7-20-finalize.service
OnFailure=census-L7-20-finalize.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/bL7/ctp
ExecStart=/usr/local/bin/census-L7-20-run
StandardOutput=append:/data/logs/L7-20.log
StandardError=append:/data/logs/L7-20.log
Restart=no
# an OOM kill of one project must not stop the whole census (systemd default is stop)
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStopSec=300
EOF_census-L7-20.service
chmod 644 /etc/systemd/system/census-L7-20.service.new; mv -f /etc/systemd/system/census-L7-20.service.new /etc/systemd/system/census-L7-20.service
cat > /etc/systemd/system/census-L7-20-finalize.service.new <<'EOF_census-L7-20-finalize.service'
[Unit]
Description=cregit census L7-20: copy results to S3, write DONE, power off if every census finalized
RequiresMountsFor=/data

[Service]
Type=oneshot
ExecStart=/usr/local/bin/census-L7-20-finalize
TimeoutStartSec=infinity
EOF_census-L7-20-finalize.service
chmod 644 /etc/systemd/system/census-L7-20-finalize.service.new; mv -f /etc/systemd/system/census-L7-20-finalize.service.new /etc/systemd/system/census-L7-20-finalize.service
cat > /etc/systemd/system/census-L7-20-live.service.new <<'EOF_census-L7-20-live.service'
[Unit]
Description=cregit census L7-20: live status to S3

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/census-L7-20-live
TimeoutStartSec=300
EOF_census-L7-20-live.service
chmod 644 /etc/systemd/system/census-L7-20-live.service.new; mv -f /etc/systemd/system/census-L7-20-live.service.new /etc/systemd/system/census-L7-20-live.service
cat > /etc/systemd/system/census-L7-20-live.timer.new <<'EOF_census-L7-20-live.timer'
[Unit]
Description=cregit census L7-20: live status to S3 every 10 min

[Timer]
OnActiveSec=1min
OnUnitActiveSec=10min
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF_census-L7-20-live.timer
chmod 644 /etc/systemd/system/census-L7-20-live.timer.new; mv -f /etc/systemd/system/census-L7-20-live.timer.new /etc/systemd/system/census-L7-20-live.timer
cat > /etc/systemd/system/census-L7-20-wait.service.new <<'EOF_census-L7-20-wait.service'
[Unit]
Description=cregit census L7-20: wait until batch6L has started and the instance has room, then start census-L7-20
After=network-online.target
RequiresMountsFor=/data /bL7

[Service]
Type=simple
ExecStart=/usr/local/bin/census-L7-20-wait
Restart=on-failure
RestartSec=60
EOF_census-L7-20-wait.service
chmod 644 /etc/systemd/system/census-L7-20-wait.service.new; mv -f /etc/systemd/system/census-L7-20-wait.service.new /etc/systemd/system/census-L7-20-wait.service
systemctl daemon-reload
after=$(for u in $R; do echo "$u $(systemctl show $u -p MainPID -p ActiveEnterTimestamp --value | tr '\n' ' ')"; done)
[ "$before" = "$after" ] && echo "running census units unchanged by the reload ($(echo "$R" | grep -c .) units: $(echo $R | tr '\n' ' '))" || { echo "CHANGED:"; diff <(echo "$before") <(echo "$after"); }
systemctl show census-L7-20.service -p OOMPolicy -p RequiresMountsFor -p OnSuccess -p OnFailure | tr '\n' ' '; echo
echo "== power-off rule tests $(date -u +%FT%TZ) (census-other-done only; nothing powers off)"
r() { local out; out=$("$@" 2>&1); echo "rc=$? $out"; }
F=$S3/batch4/dryrun/DONE
for n in batch2 batch3L batch4 batch5L batch6L L7-20; do echo "T1 $n, real state: $(r $B/census-other-done $n | cut -c1-160)"; done
all="DONE_URL_batch2=$F UNITS_batch2= DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch4=$F UNITS_batch4= DONE_URL_batch5L=$F UNITS_batch5L="
echo "T2 batch6L, 2+3L+4+5L faked done (L7-20 missing): $(eval env $all r $B/census-other-done batch6L | cut -c1-160)"
echo "T3 batch6L, 2+3L+4+5L+L7-20 faked done: $(eval env $all DONE_URL_L7_20=$F UNITS_L7_20= r $B/census-other-done batch6L | cut -c1-160)"
echo "T4 L7-20, 2+3L+4+5L+6L faked done: $(eval env $all DONE_URL_batch6L=$F UNITS_batch6L= r $B/census-other-done L7-20 | cut -c1-160)"
echo "T5 L7-20, all faked but L7-20's own waiter counted for batch2: $(eval env $all DONE_URL_batch6L=$F UNITS_batch6L= DONE_URL_L7_20=$F UNITS_L7_20=census-L7-20-wait.service UNITS_batch2=census-batch2.service r $B/census-other-done batch6L | cut -c1-160)"
echo "T6 bad argument: $(r $B/census-other-done L9 | cut -c1-120)"
for f in census-batch2-finalize census-batch3L-finalize census-batch4-finalize census-batch5L-finalize census-batch6L-finalize census-L7-20-finalize; do echo "T7 $f --decide-only: $($B/$f --decide-only 2>&1 | tail -1 | cut -c1-170)"; done
echo "T8 guard (real run): $($B/census-batch4-guard)"
echo "== waiter tests (--decide-only; nothing starts)"
echo "W1 real state: $(r $B/census-L7-20-wait --decide-only | cut -c1-400)"
ok="COUNTS_batch2='1 0' COUNTS_batch3L='1 0' COUNTS_batch4p1='1 0' COUNTS_batch4p2='1 0' COUNTS_batch4p3='1 0' COUNTS_batch5L='2 0' COUNTS_batch6L='3 0' MEMAVAIL_GB=200 DATAFREE_GB=3000 B6L_STARTED=1 INPUT_OK=1"
w() { eval env $ok "$@" $B/census-L7-20-wait --decide-only 2>&1 | sed 's/.*;\(.*\)$/\1/'; }
echo "W2 all met, gate ok: $(w GATE_OK=1) rc=$(eval env $ok GATE_OK=1 $B/census-L7-20-wait --decide-only >/dev/null 2>&1; echo $?)"
echo "W3 gate missing: $(w GATE_OK=0)"
echo "W4 batch6L not started: $(w GATE_OK=1 B6L_STARTED=0)"
echo "W5 11 other running: $(w GATE_OK=1 COUNTS_batch6L="'4 0'")"
echo "W6 memory 100G: $(w GATE_OK=1 MEMAVAIL_GB=100)"
echo "W7 /data 2000G: $(w GATE_OK=1 DATAFREE_GB=2000)"
echo "W8 inputs missing: $(w GATE_OK=1 INPUT_OK=0)"
echo "W9 batch 4 inactive (counts ignored): $(w GATE_OK=1 ACTIVE_batch4p1=inactive COUNTS_batch4p1="'9 9'")"
bash -n $B/census-backup && echo "census-backup syntax ok; RUNS: $(sed -n '/^RUNS=/,/"$/p' $B/census-backup | cut -d'|' -f1 | tr -d 'RUNS="' | tr '\n' ' ')"
