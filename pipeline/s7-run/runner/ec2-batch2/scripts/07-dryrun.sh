set -uo pipefail
CTP=/home/ec2-user/ctp-check OUT=/data/ec2-check/out CLOG=/data/logs/check.log CTP_CONFIG=/home/ec2-user/ctp-check.cfg \
  MANIFEST=/home/ec2-user/batch2-input/manifest.libexpat.tsv /usr/local/bin/census-batch2-finalize --dry-run
echo "finalize dry-run rc=$?"
aws s3 ls s3://${RUNNER_BUCKET}/batch2/dryrun/ --recursive | awk '{print $3, $4}' | head -40
echo ---; aws s3 cp s3://${RUNNER_BUCKET}/batch2/dryrun/DONE - | head -12
echo --- live; sudo -u ec2-user /usr/local/bin/census-batch2-live; echo "live rc=$?"; aws s3 cp s3://${RUNNER_BUCKET}/batch2/live/progress.txt -
systemctl is-active census-batch2.service; uptime
