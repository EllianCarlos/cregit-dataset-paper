# libexpat identity check for batch 4 on /b4p1: own ctp clone /b4p1/ctp-check, scratch output
# /b4p1/libexpat-check/out, the same flags as the batch 2 check. Parquet sha256 must be 40511e0d...fc5d.
set -uo pipefail
export AWS_PAGER=""
WANT=40511e0de1a285b5bbc4ae0ff277e4775c5d67709966dd7c64dc9163c638fc5d
echo "fstrim: $(fstrim -v /b4p3 2>&1); image /b4p3 now $(du -BM /data/loop/b4p3.img | cut -f1)"
cat > /home/ec2-user/check-b4.sh <<'U'
set -uo pipefail
C=/b4p1/ctp-check
[ -d $C ] || git clone -q /home/ec2-user/batch2-input/ctp.bundle $C -b feat/e2e-runner
cd $C; [ "$(git rev-parse --short HEAD)" = ca113e3 ] || { echo "wrong ctp HEAD"; exit 1; }
[ -x .venv/bin/python ] || { python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; }
export CTP_CONFIG=/home/ec2-user/census-batch4-check.cfg
mkdir -p /b4p1/libexpat-check/out /data/logs
I=/home/ec2-user/batch2-input
.venv/bin/python ctp.py census --manifest $I/manifest.libexpat.tsv --project-meta $I/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10 > /data/logs/check-b4.log 2>&1
echo "census rc=$?"; tail -2 /data/logs/check-b4.log
echo "cregit HEAD $(git -C /data/cregit-ec2 rev-parse HEAD)"
U
chown ec2-user: /home/ec2-user/check-b4.sh
t0=$(date +%s)
sudo -u ec2-user -i bash /home/ec2-user/check-b4.sh
got=$(sha256sum /b4p1/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet 2>/dev/null | cut -d' ' -f1)
echo "check took $(( $(date +%s) - t0 ))s"
echo "libexpat Parquet sha256 $got"
[ "$got" = "$WANT" ] && echo "CHECK OK" || echo "CHECK FAILED"
systemctl is-active census-batch2.service census-batch3L.service
