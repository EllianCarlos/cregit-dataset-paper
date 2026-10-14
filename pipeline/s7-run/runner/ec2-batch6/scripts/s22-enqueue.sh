set -uo pipefail
X=$(cat /etc/cregit-census/fed/half)
/usr/local/bin/census-fed-workload batch22 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 | cut -c1-80 || exit 1
/usr/local/bin/census-fed-enqueue batch22 $X 2>&1 | grep -v "^queued [0-9]* parts"; echo "rc=${PIPESTATUS[0]}"
echo "queue: $(grep -c . /etc/cregit-census/fed/queue) parts; first: $(head -1 /etc/cregit-census/fed/queue); last 4: $(tail -4 /etc/cregit-census/fed/queue | tr "
" ",")"
echo "censuses: $(tr "
" " " < /etc/cregit-census/censuses)  slots: $(cat /etc/cregit-census/fed/slots 2>/dev/null || echo default) / $(cat /etc/cregit-census/fed/worker_slots 2>/dev/null || echo default)  PAUSE: $(cat /etc/cregit-census/fed/PAUSE 2>/dev/null || echo none)"
echo "feeder: $(cat /run/census-fed-feeder.status)"
