#!/usr/bin/env bash
# M0-plainblame-count.sh (run by the user: `! bash ~/s3-work/dataset-x1k/M0-plainblame-count.sh`):
# downloads only the pipeline logs of the x1k done set (done-full/<p>/state/logs/pipeline-*.log, about
# 7,200 projects, some 100s of MB) to ~/s3-work/dataset-x1k/merge/logs/ and writes
# ~/s3-work/dataset-x1k/merge/plainblame.x1k.tsv: project, newest pipeline log, PLAIN-BLAME lines in it.
# Machine B rows: use plain_blame_files (the newest log = the attempt that made the Parquet; a retry
# starts again at step 2 and drops blame/). Machine A rows: use plain_blame_all_logs (resumed attempts
# keep blame/ from step 7). Read-only on S3. Run it again after machine A ends.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}/dataset-x1k/done-full
D=~/s3-work/dataset-x1k/merge; mkdir -p $D/logs
aws s3 sync $B/ $D/logs/ --exclude '*' --include '*/state/logs/pipeline-*.log' --only-show-errors
{ printf 'project\tlog\tplain_blame_files\tplain_blame_all_logs\n'
  for d in $D/logs/*/; do p=$(basename "$d")
    lg=$(ls "$d"state/logs/pipeline-2*.log 2>/dev/null | sort | tail -1) || true
    [ -n "$lg" ] || { printf '%s\t-\tNA\tNA\n' "$p"; continue; }
    printf '%s\t%s\t%s\t%s\n' "$p" "$(basename "$lg")" "$(grep -a -c 'PLAIN-BLAME ' "$lg" || true)" "$(cat "$d"state/logs/pipeline-2*.log | grep -a -c 'PLAIN-BLAME ' || true)"
  done; } > $D/plainblame.x1k.tsv
echo "projects: $(($(wc -l < $D/plainblame.x1k.tsv) - 1)); with PLAIN-BLAME: $(awk -F'\t' 'NR>1 && $3>0' $D/plainblame.x1k.tsv | wc -l); files: $(awk -F'\t' 'NR>1 && $3!="NA" {s+=$3} END {print s+0}' $D/plainblame.x1k.tsv)"
echo "written: $D/plainblame.x1k.tsv"
