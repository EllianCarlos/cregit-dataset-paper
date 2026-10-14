# restore-inputs.sh (after the layout, on an instance from the batch 3 AMI): inputs, the checked
# cregit tree from the AMI, the same no-op build step as batch 2.
set +x
aws s3 cp s3://${RUNNER_BUCKET}/batch2/input/ /data/input/ --recursive --only-show-errors
(cd /data/input && sha256sum --quiet -c SHA256SUMS) && echo "batch2 inputs sha256 ok"
mkdir -p /data/input3; aws s3 cp s3://${RUNNER_BUCKET}/batch3/input/ /data/input3/ --recursive --only-show-errors
(cd /data/input3 && sha256sum --quiet -c SHA256SUMS) && echo "batch3 inputs sha256 ok"
[ -d /data/cregit-ec2 ] || cp -a /opt/cregit-ec2.checked /data/cregit-ec2
for d in /data /data[0-9]*; do [ -d $d ] && chown -R ec2-user:ec2-user $d/; done
sudo -u ec2-user -i bash /home/ec2-user/build.sh 2>&1 | grep -v -e '^• ' -e '^✓' | tail -4
