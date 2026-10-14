# t1-feeder-stub.sh: tests of census-spot-decide (fed word) and census-fed-feeder with stub parts:
# a test FED_DIR, stub init/check, a stub start (a transient systemd unit running sleep), no census.
# Nothing touches /etc/cregit-census/fed, the census units or /run/census-spot-interrupted.
set +e
export AWS_PAGER=""
B=s3://${RUNNER_BUCKET}; IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
T=/etc/cregit-census/fedtest-$(date +%s); mkdir -p $T/wl /root/fedtest; export FED_DIR=$T FED_INPUT=$T/input
r() { local d=$1; shift; out=$("$@" 2>&1); echo "$d: rc=$? $(echo "$out" | tail -1 | cut -c1-200)"; }
echo "== $(date -u +%FT%TZ) $IID test dir $T"
# --- decide
printf 'batch99 a1\n' > $T/queue; : > $T/started
printf 'ID=batch99a1\nWL=batch99\nPART=a1\n' > $T/batch99a1.env
r "D0 real state, real censuses" /usr/local/bin/census-spot-decide
r "D1 fed, 1 part queued" env CENSUSES=fed /usr/local/bin/census-spot-decide
: > $T/queue; echo batch99a1 > $T/started
r "D2 fed, queue empty, started a1 without DONE" env CENSUSES=fed /usr/local/bin/census-spot-decide
echo "fake DONE for the t1 test" | aws s3 cp - $B/s6test/$IID/batch99/a1/final/$IID/DONE --only-show-errors
r "D3 fed, DONE present (fake prefix)" env CENSUSES=fed BUCKET_DONE=$B/s6test/$IID /usr/local/bin/census-spot-decide
systemd-run --quiet --unit=census-fedtest-hold.service sleep 30
r "D4 fed, DONE present, a part unit active" env CENSUSES=fed BUCKET_DONE=$B/s6test/$IID UNITS_fed=census-fedtest-hold.service /usr/local/bin/census-spot-decide
r "D5 b3 b5 fed, real b3/b5 units" env CENSUSES="b3 b5 fed" BUCKET_DONE=$B/s6test/$IID /usr/local/bin/census-spot-decide
r "D6 unknown word" env CENSUSES="b9" /usr/local/bin/census-spot-decide
# --- feeder with stubs
cat > /root/fedtest/init <<'S'
#!/bin/bash
printf 'ID=%s\nWL=%s\nPART=%s\n' $1$2 $1 $2 > $FED_DIR/$1$2.env; echo "stub init $1$2"
S
cat > /root/fedtest/check <<'S'
#!/bin/bash
echo "stub CHECK OK $1"
S
cat > /root/fedtest/start <<'S'
#!/bin/bash
# stub part: a transient unit that sleeps (a1 20 s, the others 300 s)
d=300; case $1 in *a1.service) d=20 ;; esac
systemd-run --quiet --unit=$1 -p RequiresMountsFor=/data sleep $d
S
chmod 755 /root/fedtest/*
export B5_ENV="" FEED_INIT=/root/fedtest/init FEED_CHECK=/root/fedtest/check FEED_START=/root/fedtest/start FEED_UNIT="census-fedtest-%s.service" FEED_RUNMAN=0
: > $T/started; echo 2 > $T/slots
printf 'CREGIT_COMMIT=pending\n' > $T/wl/batch98.env
printf 'CREGIT_COMMIT=%s\n' $(sudo -u ec2-user git -C /data/cregit-ec2 rev-parse HEAD) > $T/wl/batch99.env
printf 'batch98 a1\nbatch99 a1\n' > $T/queue
r "F1 head part's workload commit pending" /usr/local/bin/census-fed-feeder
echo "   started: [$(cat $T/started | tr '\n' ' ')] queue: [$(tr '\n' ',' < $T/queue)]"
printf 'batch99 a1\nbatch99 a2\nbatch99 a3\n' > $T/queue
r "F8 dry run" /usr/local/bin/census-fed-feeder --dry-run
r "F9 memory floor" env MINMEM_GB=100000 /usr/local/bin/census-fed-feeder
touch $T/PAUSE; r "F3 PAUSE" /usr/local/bin/census-fed-feeder; rm -f $T/PAUSE
r "F2 3 queued, 2 slots" /usr/local/bin/census-fed-feeder
echo "   started: [$(cat $T/started | tr '\n' ' ')] queue: [$(tr '\n' ',' < $T/queue)] units: $(systemctl is-active census-fedtest-batch99a1.service census-fedtest-batch99a2.service | tr '\n' ' ')"
r "F2b again while both run" /usr/local/bin/census-fed-feeder
r "D7 decide while a part is queued" env CENSUSES=fed UNITS_fed= /usr/local/bin/census-spot-decide
sleep 25
r "F5 after a1 ended" /usr/local/bin/census-fed-feeder
echo "   started: [$(cat $T/started | tr '\n' ' ')] queue: [$(tr '\n' ',' < $T/queue)] units: $(systemctl is-active census-fedtest-batch99a1.service census-fedtest-batch99a2.service census-fedtest-batch99a3.service | tr '\n' ' ')"
r "F5b queue empty" /usr/local/bin/census-fed-feeder
r "D8 decide, queue empty, stub units active" env CENSUSES=fed UNITS_fed="census-fedtest-batch99a2.service census-fedtest-batch99a3.service" BUCKET_DONE=$B/s6test/$IID /usr/local/bin/census-spot-decide
printf 'batch99 a4\n' > $T/queue
echo 4 > $T/slots
r "F7 check fails" env FEED_CHECK=/bin/false /usr/local/bin/census-fed-feeder
echo "   PAUSE: $(cat $T/PAUSE 2>/dev/null) | started: [$(cat $T/started | tr '\n' ' ')] queue: [$(tr '\n' ',' < $T/queue)]"
r "F7b paused afterwards" /usr/local/bin/census-fed-feeder
systemctl stop census-fedtest-batch99a2.service census-fedtest-batch99a3.service census-fedtest-hold.service 2>/dev/null
echo "== feeder log"; tail -n 12 $T/feeder.log | cut -c1-160
echo "== real fed dir untouched: $(ls /etc/cregit-census/fed 2>&1 | tr '\n' ' ')  censuses: $(tr '\n' ' ' < /etc/cregit-census/censuses)  interrupted: $(ls /run/census-spot-interrupted 2>&1 | cut -c1-60)"
systemctl is-active $(systemctl list-units --no-legend --plain 'census-b*@*.service' | awk '{print $1}') | sort | uniq -c
