set -uo pipefail
X=$(cat /etc/cregit-census/fed/half)
/usr/local/bin/census-fed-workload batch7 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 >/dev/null || exit 1
/usr/local/bin/census-fed-enqueue batch7 $X 2>&1 | grep -E 'queued [0-9]+ parts|FAIL|DIFFERS|sha256 ok' || exit 1
/usr/local/bin/census-fed-workload batch8 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 >/dev/null || exit 1
/usr/local/bin/census-fed-enqueue batch8 $X 2>&1 | grep -E 'queued [0-9]+ parts|FAIL|DIFFERS|sha256 ok' || exit 1
/usr/local/bin/census-fed-workload batch9 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 >/dev/null || exit 1
/usr/local/bin/census-fed-enqueue batch9 $X 2>&1 | grep -E 'queued [0-9]+ parts|FAIL|DIFFERS|sha256 ok' || exit 1
/usr/local/bin/census-fed-workload batch10 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 >/dev/null || exit 1
/usr/local/bin/census-fed-enqueue batch10 $X 2>&1 | grep -E 'queued [0-9]+ parts|FAIL|DIFFERS|sha256 ok' || exit 1
/usr/local/bin/census-fed-workload batch11 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 >/dev/null || exit 1
/usr/local/bin/census-fed-enqueue batch11 $X 2>&1 | grep -E 'queued [0-9]+ parts|FAIL|DIFFERS|sha256 ok' || exit 1
/usr/local/bin/census-fed-workload batch12 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 >/dev/null || exit 1
/usr/local/bin/census-fed-enqueue batch12 $X 2>&1 | grep -E 'queued [0-9]+ parts|FAIL|DIFFERS|sha256 ok' || exit 1
/usr/local/bin/census-fed-workload batch13 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 >/dev/null || exit 1
/usr/local/bin/census-fed-enqueue batch13 $X 2>&1 | grep -E 'queued [0-9]+ parts|FAIL|DIFFERS|sha256 ok' || exit 1
/usr/local/bin/census-fed-workload batch14 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 >/dev/null || exit 1
/usr/local/bin/census-fed-enqueue batch14 $X 2>&1 | grep -E 'queued [0-9]+ parts|FAIL|DIFFERS|sha256 ok' || exit 1
/usr/local/bin/census-fed-workload batch15 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 >/dev/null || exit 1
/usr/local/bin/census-fed-enqueue batch15 $X 2>&1 | grep -E 'queued [0-9]+ parts|FAIL|DIFFERS|sha256 ok' || exit 1
/usr/local/bin/census-fed-workload batch16 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 >/dev/null || exit 1
/usr/local/bin/census-fed-enqueue batch16 $X 2>&1 | grep -E 'queued [0-9]+ parts|FAIL|DIFFERS|sha256 ok' || exit 1
/usr/local/bin/census-fed-workload batch17 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 >/dev/null || exit 1
/usr/local/bin/census-fed-enqueue batch17 $X 2>&1 | grep -E 'queued [0-9]+ parts|FAIL|DIFFERS|sha256 ok' || exit 1
/usr/local/bin/census-fed-workload batch18 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 >/dev/null || exit 1
/usr/local/bin/census-fed-enqueue batch18 $X 2>&1 | grep -E 'queued [0-9]+ parts|FAIL|DIFFERS|sha256 ok' || exit 1
/usr/local/bin/census-fed-workload batch19 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 >/dev/null || exit 1
/usr/local/bin/census-fed-enqueue batch19 $X 2>&1 | grep -E 'queued [0-9]+ parts|FAIL|DIFFERS|sha256 ok' || exit 1
/usr/local/bin/census-fed-workload batch20 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 >/dev/null || exit 1
/usr/local/bin/census-fed-enqueue batch20 $X 2>&1 | grep -E 'queued [0-9]+ parts|FAIL|DIFFERS|sha256 ok' || exit 1
echo "queue: $(grep -c . /etc/cregit-census/fed/queue) parts; first: $(head -1 /etc/cregit-census/fed/queue); last: $(tail -1 /etc/cregit-census/fed/queue)"
for f in /etc/cregit-census/fed/wl/*.env; do echo "$(basename $f .env) $(grep -o "CREGIT_COMMIT=.\{7\}" $f) $(grep -o "WANT_PQ=.\{8\}" $f)"; done | tr "
" " "; echo
/usr/local/bin/census-spot-decide; echo "decide rc=$?"
