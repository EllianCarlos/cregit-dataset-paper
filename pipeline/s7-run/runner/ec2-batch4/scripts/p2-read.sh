set +e
export AWS_PAGER=""
for f in /home/ec2-user/check.sh /home/ec2-user/ctp-check.cfg /usr/local/bin/census-batch2-run /etc/systemd/system/census-batch2.service /etc/systemd/system/census-batch2-finalize.service; do echo "## $f"; cat $f; done
ls -la /data/input/ 2>&1 | head; grep ctp.bundle /home/ec2-user/batch2-input/SHA256SUMS; sha256sum /home/ec2-user/batch2-input/ctp.bundle /data/input/ctp.bundle 2>&1
python3.12 --version; ls /data/ec2-check/ 2>&1
