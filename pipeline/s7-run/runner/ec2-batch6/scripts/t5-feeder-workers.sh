# t5-feeder-workers.sh: the feeder's worker count with stub parts (test FED_DIR, no census), then a
# dry run on the real fed dir (prints the real parts and busy workers; changes nothing).
set +e
T=/etc/cregit-census/fedtest-w-$(date +%s); mkdir -p $T/wl /root/fedtest; export FED_DIR=$T FED_INPUT=$T/input
cat > /root/fedtest/init <<'S'
#!/bin/bash
printf 'ID=%s\nWL=%s\nPART=%s\nWORKERS=4\n' $1$2 $1 $2 > $FED_DIR/$1$2.env; echo "stub init $1$2"
S
printf '#!/bin/bash\necho "stub CHECK OK $1"\n' > /root/fedtest/check
printf '#!/bin/bash\nsystemd-run --quiet --unit=$1 sleep 120\n' > /root/fedtest/start
chmod 755 /root/fedtest/*
export B5_ENV="" FEED_INIT=/root/fedtest/init FEED_CHECK=/root/fedtest/check FEED_START=/root/fedtest/start FEED_UNIT="census-fedtw-%s.service" FEED_RUNMAN=0
printf 'CREGIT_COMMIT=x\n' > $T/wl/batch99.env; : > $T/started
for i in 1 2 3 4 5 6 7 8 9 10; do echo "batch99 w$i"; done > $T/queue
echo "W1 counts '4 0' (full parts): $(FEED_COUNTS='4 0' /usr/local/bin/census-fed-feeder | tail -1)"
echo "   started: $(tr '\n' ' ' < $T/started)"
echo "W2 counts '1 0' (tails): $(FEED_COUNTS='1 0' /usr/local/bin/census-fed-feeder | tail -1)"
echo "   started: $(tr '\n' ' ' < $T/started)"
echo "W3 worker_slots 30, counts '1 0': $(echo 30 > $T/worker_slots; FEED_COUNTS='1 0' /usr/local/bin/census-fed-feeder | tail -1)"
echo "W4 unreadable counts = 4 each: $(rm $T/worker_slots; echo 20 > $T/slots; FEED_COUNTS='x y' /usr/local/bin/census-fed-feeder | tail -1)"
for u in $(systemctl list-units --no-legend --plain 'census-fedtw-*' | awk '{print $1}'); do systemctl stop $u; done
unset FED_DIR FED_INPUT B5_ENV FEED_INIT FEED_CHECK FEED_START FEED_UNIT FEED_RUNMAN
echo "R real dir, dry run: $(/usr/local/bin/census-fed-feeder --dry-run | tail -1)"
