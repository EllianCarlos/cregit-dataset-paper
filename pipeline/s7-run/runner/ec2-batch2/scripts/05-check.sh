set -uo pipefail
mkdir -p /home/ec2-user/batch2-input && cp -p /data/input/* /home/ec2-user/batch2-input/ && chown -R ec2-user: /home/ec2-user/batch2-input
cat > /home/ec2-user/ctp-check.cfg <<'C'
# EC2 half of the machine-independence check (cregit 95cdc88); own ctp clone and output.
[paths]
cregit_dir = /data/cregit-ec2
output_dir = /data/ec2-check/out
C
cat > /home/ec2-user/check.sh <<'U'
set -uo pipefail
cd ~/ctp-check
export CTP_CONFIG=/home/ec2-user/ctp-check.cfg
I=/home/ec2-user/batch2-input
.venv/bin/python ctp.py census --manifest $I/manifest.libexpat.tsv --project-meta $I/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10 > /data/logs/check.log 2>&1
echo "census rc=$?"; tail -3 /data/logs/check.log
echo "cregit HEAD $(git -C /data/cregit-ec2 rev-parse HEAD)"
sha256sum /data/ec2-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet
ls -la /data/ec2-check/out/libexpat__libexpat/
U
chown ec2-user: /home/ec2-user/check.sh /home/ec2-user/ctp-check.cfg
sudo -u ec2-user -i bash /home/ec2-user/check.sh
