#!/usr/bin/env bash
# C1-status.sh (this machine, read-only: ec2 describe and s3 ls; it downloads nothing): the machines of
# the split and, per part, the batches in S3 (complete = with .sha256), the newest batch time, the
# age of status.txt and the end markers; and the control files.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
S=s3://${RUNNER_BUCKET}/dataset-x1k/rust-split
echo "== $(date -u +%FT%TZ) C1"
aws ec2 describe-instances --filters Name=tag:Run,Values=rust-split \
  --query 'Reservations[].Instances[].[Tags[?Key==`Part`]|[0].Value,InstanceId,InstanceType,State.Name,Tags[?Key==`Name`]|[0].Value,LaunchTime]' \
  --output text | sort -n | sed 's/^/  /'
aws s3 ls --recursive "$S/out/" > /tmp/rs-c1.txt 2>/dev/null || true
now=$(date +%s)
for k in $(awk '{print $4}' /tmp/rs-c1.txt | sed -n 's#^dataset-x1k/rust-split/out/\([0-9]*\)/.*#\1#p' | sort -un); do
  p="dataset-x1k/rust-split/out/$k/"
  nb=$(grep -c " ${p}batches/b-[0-9]*\.sha256$" /tmp/rs-c1.txt || true)
  newest=$(grep " ${p}batches/b-[0-9]*\.sha256$" /tmp/rs-c1.txt | sort | tail -1 | awk '{print $1 "T" $2}')
  st=$(grep " ${p}status.txt$" /tmp/rs-c1.txt | awk '{print $1 " " $2}')
  age=$([ -n "$st" ] && echo $(( (now - $(date -d "$st" +%s)) / 60 ))min || echo none)
  mk=$(for m in DONE STOPPED GATE-FAILED ALERT; do grep -q " ${p}$m$" /tmp/rs-c1.txt && echo -n "$m "; done)
  echo "  part $k: complete batches $nb (newest ${newest:-none}); status.txt age $age; markers ${mk:-none}; gate.txt $(grep -q " ${p}gate.txt$" /tmp/rs-c1.txt && echo yes || echo no)"
done
echo "  control: $(aws s3 ls "$S/control/" 2>/dev/null | awk '{print $4 " (" $1 " " $2 ")"}' | tr '\n' ' ')"
echo "  input: $(aws s3 ls "$S/input/SHA256SUMS" 2>/dev/null | awk '{print $1 " " $2}' || echo none); clone.tar.zst $(aws s3 ls "$S/input/clone.tar.zst" 2>/dev/null | awk '{print int($3 / 1000000) " MB"}')"
rm -f /tmp/rs-c1.txt
