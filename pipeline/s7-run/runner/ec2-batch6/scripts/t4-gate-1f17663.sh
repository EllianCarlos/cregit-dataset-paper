# t4-gate-1f17663.sh: the real part-init (bundle fetch, checkout of 1f17663) and identity gate of a fed
# part on a TEST workload (batch97, part j1; test dirs, no census), before the first batch 7 part needs it.
set +e
export AWS_PAGER=""
X=$(cat /etc/cregit-census/fed/half)
export FED_DIR=/etc/cregit-census/fedtest-1f17663 FED_INPUT=/home/ec2-user/fedtest-input
mkdir -p $FED_DIR $FED_INPUT/batch97; echo $X > $FED_DIR/half
printf 'half\tworkload\tpart\tworkers\tprojects\tpredicted_h\tsha256\n%s\tbatch97\tj1\t4\t1\t0.1\ttest\n' $X > $FED_INPUT/batch97/parts.batch97.tsv
echo "== $(date -u +%FT%TZ) $(cat /sys/devices/virtual/dmi/id/board_asset_tag)"
/usr/local/bin/census-fed-workload batch97 --commit 1f176633675eb836e322bf66bcf87343e98c98e1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-1f17663.bundle --bundle-sha256 a827082e73bb435fcf05c1a97380e39ee467ca45c4a8d9e1045a3f3afe153486 --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799 | cut -c1-120
t0=$(date +%s); /usr/local/bin/census-fed-part-init batch97 j1 | cut -c1-220; echo "part-init rc=${PIPESTATUS[0]} ($(( $(date +%s) - t0 )) s)"
ls -la /data/input/cregit-1f17663.bundle | cut -c1-120
sudo -u ec2-user git -C /w/batch97j1/cregit-ec2 log --oneline -3
t0=$(date +%s); /usr/local/bin/census-fed-check batch97j1 | tail -4; echo "check rc=${PIPESTATUS[0]} ($(( $(date +%s) - t0 )) s)"
ls -l /w/batch97j1/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet | awk '{print $5, $NF}'
