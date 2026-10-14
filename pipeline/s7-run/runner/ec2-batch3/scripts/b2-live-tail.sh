set -uo pipefail
B=/usr/local/bin
[ -e $B/census-batch2-live.orig-20261009 ] || cp -p $B/census-batch2-live $B/census-batch2-live.orig-20261009
bash -n $B/census-batch2-live && python3 -m py_compile $B/census-steps && echo syntax ok
rm -rf $B/__pycache__
sudo -u ec2-user $B/census-batch2-live; echo "live rc=$?"
aws s3 cp s3://${RUNNER_BUCKET}/batch2/live/steps.txt - | cut -c1-200
systemctl is-active census-batch2.service; systemctl list-timers census-batch2-live.timer --no-pager | sed -n 2p
