set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin; S3=s3://${RUNNER_BUCKET}
U=$(systemctl list-units --no-legend --plain --all 'census*' | awk '{print $1}')
for u in $U; do [ "$(systemctl show $u -p NeedDaemonReload --value)" = no ] || { echo "$u: NeedDaemonReload=yes; aborting"; exit 1; }; done
echo "NeedDaemonReload=no for all $(echo $U | wc -w) loaded census units"
R=$(systemctl list-units --no-legend --plain --state=active 'census*.service' | awk '{print $1}')
before=$(for u in $R; do echo "$u $(systemctl show $u -p MainPID -p ActiveEnterTimestamp --value | tr '\n' ' ')"; done)
cat > /etc/systemd/system/census-L1r.service.new <<'EOF_census-L1r.service'
[Unit]
Description=cregit census L1r: batch 1 rerun, L (torvalds__linux, SAP__project-foxhound), 2 workers (ctp census, loop XFS /bL1r)
Wants=network-online.target
After=network-online.target nix-daemon.service
RequiresMountsFor=/data /bL1r
OnSuccess=census-L1r-finalize.service
OnFailure=census-L1r-finalize.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/bL1r/ctp
ExecStart=/usr/local/bin/census-L1r-run
StandardOutput=append:/data/logs/L1r.log
StandardError=append:/data/logs/L1r.log
Restart=no
# an OOM kill of one project must not stop the whole census (systemd default is stop)
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStopSec=300
EOF_census-L1r.service
chmod 644 /etc/systemd/system/census-L1r.service.new; mv -f /etc/systemd/system/census-L1r.service.new /etc/systemd/system/census-L1r.service
cat > /etc/systemd/system/census-L1r-finalize.service.new <<'EOF_census-L1r-finalize.service'
[Unit]
Description=cregit census L1r: copy results to S3, write DONE, power off if every census finalized
RequiresMountsFor=/data

[Service]
Type=oneshot
ExecStart=/usr/local/bin/census-L1r-finalize
TimeoutStartSec=infinity
EOF_census-L1r-finalize.service
chmod 644 /etc/systemd/system/census-L1r-finalize.service.new; mv -f /etc/systemd/system/census-L1r-finalize.service.new /etc/systemd/system/census-L1r-finalize.service
cat > /etc/systemd/system/census-L1r-live.service.new <<'EOF_census-L1r-live.service'
[Unit]
Description=cregit census L1r: live status to S3

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/census-L1r-live
TimeoutStartSec=300
EOF_census-L1r-live.service
chmod 644 /etc/systemd/system/census-L1r-live.service.new; mv -f /etc/systemd/system/census-L1r-live.service.new /etc/systemd/system/census-L1r-live.service
cat > /etc/systemd/system/census-L1r-live.timer.new <<'EOF_census-L1r-live.timer'
[Unit]
Description=cregit census L1r: live status to S3 every 10 min

[Timer]
OnActiveSec=1min
OnUnitActiveSec=10min
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF_census-L1r-live.timer
chmod 644 /etc/systemd/system/census-L1r-live.timer.new; mv -f /etc/systemd/system/census-L1r-live.timer.new /etc/systemd/system/census-L1r-live.timer
cat > /etc/systemd/system/census-L1r-wait.service.new <<'EOF_census-L1r-wait.service'
[Unit]
Description=cregit census L1r: wait until the big EC2 has room and the gate passed, then start census-L1r
After=network-online.target
RequiresMountsFor=/data /bL1r

[Service]
Type=simple
ExecStart=/usr/local/bin/census-L1r-wait
Restart=on-failure
RestartSec=60
EOF_census-L1r-wait.service
chmod 644 /etc/systemd/system/census-L1r-wait.service.new; mv -f /etc/systemd/system/census-L1r-wait.service.new /etc/systemd/system/census-L1r-wait.service
cat > /etc/systemd/system/census-L1r-firm.service.new <<'EOF_census-L1r-firm.service'
[Unit]
Description=cregit census L1r: oom_score_adj -500 on the firm step of census L1r

[Service]
Type=oneshot
ExecStart=/usr/local/bin/census-L1r-firm
TimeoutStartSec=60
EOF_census-L1r-firm.service
chmod 644 /etc/systemd/system/census-L1r-firm.service.new; mv -f /etc/systemd/system/census-L1r-firm.service.new /etc/systemd/system/census-L1r-firm.service
cat > /etc/systemd/system/census-L1r-firm.timer.new <<'EOF_census-L1r-firm.timer'
[Unit]
Description=cregit census L1r: protect the firm step from the OOM killer every 30 s

[Timer]
OnActiveSec=30s
OnUnitActiveSec=30s
AccuracySec=5s

[Install]
WantedBy=timers.target
EOF_census-L1r-firm.timer
chmod 644 /etc/systemd/system/census-L1r-firm.timer.new; mv -f /etc/systemd/system/census-L1r-firm.timer.new /etc/systemd/system/census-L1r-firm.timer
systemctl daemon-reload
after=$(for u in $R; do echo "$u $(systemctl show $u -p MainPID -p ActiveEnterTimestamp --value | tr '\n' ' ')"; done)
[ "$before" = "$after" ] && echo "running census units unchanged by the reload ($(echo "$R" | grep -c .) units: $(echo $R | tr '\n' ' '))" || { echo "CHANGED:"; diff <(echo "$before") <(echo "$after"); }
systemctl show census-L1r.service -p OOMPolicy -p RequiresMountsFor -p OnSuccess -p OnFailure | tr '\n' ' '; echo
echo "== power-off rule tests $(date -u +%FT%TZ) (census-other-done only; nothing powers off)"
F=$S3/batch4/dryrun/DONE
t() { local d=$1 self=$2; shift 2; out=$( ( [ $# -gt 0 ] && export "$@"; $B/census-other-done $self ) 2>&1); echo "$d: rc=$? $out" | cut -c1-200; }
for n in batch2 batch3L batch4 batch5L batch6L L7-20 L22 L7-20b L23 L1r; do t "T1 $n, real state" $n; done
o="DONE_URL_batch2=$F UNITS_batch2= DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch4=$F UNITS_batch4= DONE_URL_batch5L=$F UNITS_batch5L= DONE_URL_batch6L=$F UNITS_batch6L= DONE_URL_L7_20=$F UNITS_L7_20= DONE_URL_L22=$F UNITS_L22= DONE_URL_L7_20b=$F UNITS_L7_20b="
t "T2 L23, all other faked but L1r (L1r DONE missing)" L23 $o
t "T3 L23, all other faked" L23 $o DONE_URL_L1r=$F UNITS_L1r=
t "T4 L1r, all other faked" L1r $o DONE_URL_L23=$F UNITS_L23=
t "T5 L22, all other faked but L1r with an active unit" L22 $o DONE_URL_L23=$F UNITS_L23= DONE_URL_L1r=$F UNITS_L1r=census-L7-20.service
t "T6 bad argument" L9
for f in census-batch2-finalize census-batch3L-finalize census-batch4-finalize census-batch5L-finalize census-batch6L-finalize census-L7-20-finalize census-L22-finalize census-L7-20b-finalize census-L23-finalize census-L1r-finalize; do echo "T7 $f --decide-only: $($B/$f --decide-only 2>&1 | tail -1 | cut -c1-170)"; done
echo "T8 guard (real run): $($B/census-batch4-guard)"
echo "== waiter tests (--decide-only; nothing starts)"
echo "W1 real state: $($B/census-L1r-wait --decide-only 2>&1 | cut -c1-600)"
w() { local d=$1; shift; out=$( ( export ACTIVE_batch2=inactive ACTIVE_batch3L=inactive ACTIVE_batch4p1=inactive ACTIVE_batch4p2=inactive ACTIVE_batch4p3=inactive ACTIVE_batch6L=inactive ACTIVE_batch5L=active ACTIVE_L7_20=active ACTIVE_L22=active ACTIVE_L7_20b=active ACTIVE_L23=active COUNTS_batch5L='1 0' COUNTS_L7_20='4 0' COUNTS_L22='1 0' COUNTS_L7_20b='2 20' COUNTS_L23='4 4' MEMAVAIL_GB=300 DATAFREE_GB=2500 INPUT_OK=1 GATE_OK=1 STOPF=/nonexistent; [ $# -gt 0 ] && export "$@"; $B/census-L1r-wait --decide-only ) 2>&1); echo "$d: rc=$? ...${out: -100}"; }
w "W2 L23 active, 12 other running"
w "W3 L23 active, 13 other running" COUNTS_L22='2 0'
w "W4 gate missing" GATE_OK=0
w "W5 memory 100G" MEMAVAIL_GB=100
w "W6 /data 1500G" DATAFREE_GB=1500
w "W7 inputs missing" INPUT_OK=0
w "W8 L23 not started, room" ACTIVE_L23=inactive STARTED_L23=0 COUNTS_L7_20='1 0'
w "W9 L23 activating 0r/8q, 9 others (+4 slots = 13)" ACTIVE_L23=activating COUNTS_L23='0 8' COUNTS_L7_20b='3 20'
w "W10 L23 ended (started before), 8 others" ACTIVE_L23=inactive STARTED_L23=1
w "W11 L7-20b inactive (its counts ignored)" ACTIVE_L7_20b=inactive COUNTS_L7_20b='9 0' COUNTS_L22='3 0'
w "W12 STOP present" STOPF=/etc/hostname
echo "== firm protection test (fake /proc in a temp dir; no real process changes)"
FT=$(mktemp -d); mkdir -p $FT/proc/11 $FT/proc/12
printf 'python3\0/bL1r/ctp/firm_attribution.py\0/bL1r/census-2026-10-L1r/torvalds__linux/x.parquet\0' > $FT/proc/11/cmdline; echo '0::/system.slice/census-L1r.service' > $FT/proc/11/cgroup
printf 'python3\0/bL7b/ctp/firm_attribution.py\0/bL7b/census-2026-10-L7-20b/y/y.parquet\0' > $FT/proc/12/cmdline; echo '0::/system.slice/census-L7-20b.service' > $FT/proc/12/cgroup
for i in 11 12; do echo 0 > $FT/proc/$i/oom_score_adj; echo 'VmRSS: 1048576 kB' > $FT/proc/$i/status; done
PROC=$FT/proc ST=$FT/st LOG=$FT/log $B/census-L1r-firm; echo "F1 $(cat $FT/st) | adj L1r=$(cat $FT/proc/11/oom_score_adj) L7-20b=$(cat $FT/proc/12/oom_score_adj) | log: $(cat $FT/log)"; rm -rf $FT
echo "F2 real run: $($B/census-L1r-firm; cat /run/census-L1r-firm.status)"
bash -n $B/census-backup && echo "census-backup syntax ok; RUNS: $(sed -n '/^RUNS=/,/"$/p' $B/census-backup | cut -d'|' -f1 | tr -d 'RUNS="' | tr '\n' ' ')"
