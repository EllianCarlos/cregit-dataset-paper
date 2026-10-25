#!/usr/bin/env bash
# M1-x3-start.sh (the x1k links machine, root, through x3/ssm-x3.sh, after R1-x3-setup.sh): starts the
# unit x1k-links: /data/x3/tools/x3_run.sh as root (Python and aws as ec2-user), output /data/x3/run.log.
# x3_run.sh: the PLAIN-BLAME logs, the v1 and x1k downloads with sha256, the two domain caches, the v1
# gate (mapping hash 2fb053cd1ee7 of links-v4.6), the merged links, the domain reports, the PLAIN-BLAME
# count, the at-sign check, the upload of /data/x3/out to s3://B/dataset-x1k/links-work/<run>/, then
# DONE or ALERT there; DONE: shutdown -h +5 (the instance terminates), unless /home/ec2-user/NO_SHUTDOWN
# or /run/x3-hold exists. ALERT: no shutdown (look with M2-x3-check.sh).
# Defaults: JOBS nproc - 2 extraction jobs, MEM 55% of the memory / JOBS (at least 2GB) per job, TH 1,
# LMEM 32GB for build_links and the reports, MemoryMax 90% of the memory. ssm sends this file as it
# is, so change a default in this file if needed.
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_A}|${RUNNER_EC2_X1K_LONG_A2}|${RUNNER_EC2_X1K_B1}|${RUNNER_EC2_X1K_B2}|${RUNNER_EC2_X1K_LONG_A4}|${RUNNER_EC2_PATHFIX_B1}|${RUNNER_EC2_X1K_RAW_1}|${RUNNER_EC2_X1K_RAW_2}|${RUNNER_EC2_V0_ORG_1})
  echo "ABORT: $IID is not the x3 links machine"; exit 1 ;; esac
RUN=${X3_RUN:?no X3_RUN: send this script with x3/ssm-x3.sh}
B=s3://${RUNNER_BUCKET}; X=/data/x3; T=$X/tools; PY=$X/.venv/bin/python; UNIT=x1k-links
WANT_SUMS=7dba806bb9e3a1f78eb2da654f7daa870978637bff687ad6ae49ef8f9e60ba2b
NP=$(nproc); RAM=$(free -g | awk '/Mem:/{print $2}')
JOBS=${JOBS:-$((NP - 2))}; TH=${TH:-1}
MEM=${MEM:-$(( RAM * 55 / 100 / JOBS < 2 ? 2 : RAM * 55 / 100 / JOBS ))GB}; LMEM=${LMEM:-32GB}
MAX=${MAX:-$(( RAM * 90 / 100 ))G}
echo "== $(date -u +%FT%TZ) $IID run $RUN, $NP vCPU, $RAM GiB, jobs $JOBS x $MEM, threads $TH, links $LMEM, MemoryMax $MAX"
systemctl is-active -q $UNIT && { echo "ABORT: $UNIT runs"; exit 1; }
mountpoint -q /data1 || { echo "ABORT: no /data1 (run R1-x3-setup.sh)"; exit 1; }
[ "$(sha256sum $T/SHA256SUMS | cut -d' ' -f1)" = $WANT_SUMS ] || { echo "ABORT: tools SHA256SUMS is not $WANT_SUMS (run R1-x3-setup.sh)"; exit 1; }
(cd $T && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: a tool sha256"; exit 1; }
sudo -u ec2-user $PY -I -c 'import duckdb; assert duckdb.__version__ == "1.5.5"' || { echo "ABORT: no duckdb 1.5.5 in $PY"; exit 1; }
bash -n $T/x3_run.sh || { echo "ABORT: x3_run.sh syntax"; exit 1; }
if [ -f $X/out/DONE ]; then echo "ABORT: $X/out/DONE exists (this run is done)"; exit 1; fi
[ -f $X/out/ALERT ] && { mv $X/out/ALERT $X/out/ALERT.$(date -u +%Y%m%dT%H%M%SZ); echo "an earlier ALERT moved aside; start again"; }
systemctl reset-failed $UNIT 2>/dev/null || true
systemd-run --unit=$UNIT -p Nice=5 -p MemoryMax=$MAX -p OOMPolicy=continue \
  -p StandardOutput=append:$X/run.log -p StandardError=append:$X/run.log \
  --setenv=PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin --setenv=AWS_REGION=${RUNNER_AWS_REGION} \
  --setenv=RUN=$RUN --setenv=X=$X --setenv=T=$T --setenv=PY=$PY --setenv=B=$B \
  --setenv=JOBS=$JOBS --setenv=TH=$TH --setenv=MEM=$MEM --setenv=LMEM=$LMEM --setenv=LTH=8 \
  --setenv=OV=v4.6 --setenv=DB=companies.v4.6.duckdb \
  --setenv=REF_MAPPING=2fb053cd1ee73525b57c83961e59efe5ff7ebd6cda59b8abd37cb3617fe72d29 \
  --setenv=WANT_SC_V1=4023295abc589a5eb0f4124e0aa76000402bd2492755e62f50af03121f661946 \
  --setenv=WANT_SC_X1K=1520c5f4d8909b3625c73bdea3cc08f23fced0a77f3722ec0809acd80de96f35 \
  --setenv=N_V1=3544 --setenv=N_X1K=7209 --setenv=RUNAS=ec2-user \
  /bin/bash $T/x3_run.sh || { echo "ABORT: systemd-run failed"; exit 1; }
echo "START $(date -u +%FT%TZ) unit $UNIT run $RUN jobs $JOBS x $MEM threads $TH links $LMEM MemoryMax $MAX" | tee -a $X/record
sleep 60; systemctl --no-pager status $UNIT | sed -n 1,6p; tail -4 $X/run.log | cut -c1-200
echo "M1-x3 done"
