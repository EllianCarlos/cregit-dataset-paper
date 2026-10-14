set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin; S3=s3://${RUNNER_BUCKET}
U=$(systemctl list-units --no-legend --plain --all 'census*' | awk '{print $1}')
for u in $U; do [ "$(systemctl show $u -p NeedDaemonReload --value)" = no ] || { echo "$u: NeedDaemonReload=yes; aborting"; exit 1; }; done
echo "NeedDaemonReload=no for all $(echo $U | wc -w) loaded census units"
R=$(systemctl list-units --no-legend --plain --state=active 'census*.service' | awk '{print $1}')
before=$(for u in $R; do echo "$u $(systemctl show $u -p MainPID -p ActiveEnterTimestamp --value | tr '\n' ' ')"; done)
cat > /etc/systemd/system/census-L23.service.new <<'EOF_census-L23.service'
[Unit]
Description=cregit census L23: the 8 L projects of batch 23 (DP8L v4 near-miss supplement), 4 workers (ctp census, loop XFS /bL23)
Wants=network-online.target
After=network-online.target nix-daemon.service
RequiresMountsFor=/data /bL23
OnSuccess=census-L23-finalize.service
OnFailure=census-L23-finalize.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/bL23/ctp
ExecStart=/usr/local/bin/census-L23-run
StandardOutput=append:/data/logs/L23.log
StandardError=append:/data/logs/L23.log
Restart=no
# an OOM kill of one project must not stop the whole census (systemd default is stop)
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStopSec=300
EOF_census-L23.service
chmod 644 /etc/systemd/system/census-L23.service.new; mv -f /etc/systemd/system/census-L23.service.new /etc/systemd/system/census-L23.service
cat > /etc/systemd/system/census-L23-finalize.service.new <<'EOF_census-L23-finalize.service'
[Unit]
Description=cregit census L23: copy results to S3, write DONE, power off if every census finalized
RequiresMountsFor=/data

[Service]
Type=oneshot
ExecStart=/usr/local/bin/census-L23-finalize
TimeoutStartSec=infinity
EOF_census-L23-finalize.service
chmod 644 /etc/systemd/system/census-L23-finalize.service.new; mv -f /etc/systemd/system/census-L23-finalize.service.new /etc/systemd/system/census-L23-finalize.service
cat > /etc/systemd/system/census-L23-live.service.new <<'EOF_census-L23-live.service'
[Unit]
Description=cregit census L23: live status to S3

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/census-L23-live
TimeoutStartSec=300
EOF_census-L23-live.service
chmod 644 /etc/systemd/system/census-L23-live.service.new; mv -f /etc/systemd/system/census-L23-live.service.new /etc/systemd/system/census-L23-live.service
cat > /etc/systemd/system/census-L23-live.timer.new <<'EOF_census-L23-live.timer'
[Unit]
Description=cregit census L23: live status to S3 every 10 min

[Timer]
OnActiveSec=1min
OnUnitActiveSec=10min
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF_census-L23-live.timer
chmod 644 /etc/systemd/system/census-L23-live.timer.new; mv -f /etc/systemd/system/census-L23-live.timer.new /etc/systemd/system/census-L23-live.timer
cat > /etc/systemd/system/census-L23-wait.service.new <<'EOF_census-L23-wait.service'
[Unit]
Description=cregit census L23: wait until the big EC2 has room and the gate passed, then start census-L23
After=network-online.target
RequiresMountsFor=/data /bL23

[Service]
Type=simple
ExecStart=/usr/local/bin/census-L23-wait
Restart=on-failure
RestartSec=60
EOF_census-L23-wait.service
chmod 644 /etc/systemd/system/census-L23-wait.service.new; mv -f /etc/systemd/system/census-L23-wait.service.new /etc/systemd/system/census-L23-wait.service
systemctl daemon-reload
after=$(for u in $R; do echo "$u $(systemctl show $u -p MainPID -p ActiveEnterTimestamp --value | tr '\n' ' ')"; done)
[ "$before" = "$after" ] && echo "running census units unchanged by the reload ($(echo "$R" | grep -c .) units: $(echo $R | tr '\n' ' '))" || { echo "CHANGED:"; diff <(echo "$before") <(echo "$after"); }
systemctl show census-L23.service -p OOMPolicy -p RequiresMountsFor -p OnSuccess -p OnFailure | tr '\n' ' '; echo
echo "== power-off rule tests $(date -u +%FT%TZ) (census-other-done only; nothing powers off)"
F=$S3/batch4/dryrun/DONE
t() { local d=$1 self=$2; shift 2; out=$( ( [ $# -gt 0 ] && export "$@"; $B/census-other-done $self ) 2>&1); echo "$d: rc=$? $out" | cut -c1-200; }
for n in batch2 batch3L batch4 batch5L batch6L L7-20 L22 L7-20b L23; do t "T1 $n, real state" $n; done
o="DONE_URL_batch2=$F UNITS_batch2= DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch4=$F UNITS_batch4= DONE_URL_batch5L=$F UNITS_batch5L= DONE_URL_batch6L=$F UNITS_batch6L="
t "T2 L7-20b, 2+3L+4+5L+6L+L7-20+L22 faked (L23 missing)" L7-20b $o DONE_URL_L7_20=$F UNITS_L7_20= DONE_URL_L22=$F UNITS_L22=
t "T3 L7-20b, 2+3L+4+5L+6L+L7-20+L22+L23 faked" L7-20b $o DONE_URL_L7_20=$F UNITS_L7_20= DONE_URL_L22=$F UNITS_L22= DONE_URL_L23=$F UNITS_L23=
t "T4 L23, all other faked" L23 $o DONE_URL_L7_20=$F UNITS_L7_20= DONE_URL_L22=$F UNITS_L22= DONE_URL_L7_20b=$F UNITS_L7_20b=
t "T5 L22, all other faked but L23 with an active unit" L22 $o DONE_URL_L7_20=$F UNITS_L7_20= DONE_URL_L7_20b=$F UNITS_L7_20b= DONE_URL_L23=$F UNITS_L23=census-L7-20.service
t "T6 bad argument" L9
for f in census-batch2-finalize census-batch3L-finalize census-batch4-finalize census-batch5L-finalize census-batch6L-finalize census-L7-20-finalize census-L22-finalize census-L7-20b-finalize census-L23-finalize; do echo "T7 $f --decide-only: $($B/$f --decide-only 2>&1 | tail -1 | cut -c1-170)"; done
echo "T8 guard (real run): $($B/census-batch4-guard)"
echo "== waiter tests (--decide-only; nothing starts)"
echo "W1 real state: $($B/census-L23-wait --decide-only 2>&1 | cut -c1-460)"
w() { local d=$1; shift; out=$( ( export ACTIVE_batch2=inactive ACTIVE_batch3L=inactive ACTIVE_batch4p1=inactive ACTIVE_batch4p2=inactive ACTIVE_batch4p3=inactive ACTIVE_batch6L=inactive ACTIVE_batch5L=active ACTIVE_L7_20=active ACTIVE_L22=active ACTIVE_L7_20b=active COUNTS_batch5L='1 0' COUNTS_L7_20='4 0' COUNTS_L22='1 0' COUNTS_L7_20b='6 20' MEMAVAIL_GB=300 DATAFREE_GB=2500 INPUT_OK=1 GATE_OK=1; [ $# -gt 0 ] && export "$@"; $B/census-L23-wait --decide-only ) 2>&1); echo "$d: rc=$? ...${out: -80}"; }
w "W2 12 other running"
w "W3 13 other running" COUNTS_L22='2 0'
w "W4 gate missing" GATE_OK=0
w "W5 memory 100G" MEMAVAIL_GB=100
w "W6 /data 1900G" DATAFREE_GB=1900
w "W7 inputs missing" INPUT_OK=0
w "W8 L7-20b inactive (its counts ignored)" ACTIVE_L7_20b=inactive COUNTS_L7_20b='9 0' COUNTS_L22='3 0'
bash -n $B/census-backup && echo "census-backup syntax ok; RUNS: $(sed -n '/^RUNS=/,/"$/p' $B/census-backup | cut -d'|' -f1 | tr -d 'RUNS="' | tr '\n' ' ')"
