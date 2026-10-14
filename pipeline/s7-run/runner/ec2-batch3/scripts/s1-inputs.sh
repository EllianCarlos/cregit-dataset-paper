# batch 3 spot: the batch 2 code inputs (bundles, libexpat check manifest) and the batch 3 manifests.
mkdir -p /data/input3
aws s3 cp s3://${RUNNER_BUCKET}/batch3/input/ /data/input3/ --recursive --only-show-errors
(cd /data/input3 && sha256sum -c SHA256SUMS)
mkdir -p /etc/cregit-census && echo "BATCH=$X" > /etc/cregit-census/batch.env
chown -R ec2-user:ec2-user /data
