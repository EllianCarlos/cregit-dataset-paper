set +e
export AWS_PAGER=""
B=/usr/local/bin; R=/data/logs/batch4-restart-20261009.txt
WANT_SRCML=dea4467bb1b0a435e4536be13367325564b82e14ff69b478ad31bf144a8455f3
WANT_PQ=40511e0de1a285b5bbc4ae0ff277e4775c5d67709966dd7c64dc9163c638fc5d
echo "$(date -u +%FT%TZ) restart of batch 4 parts onto per-part cregit copies /b4pK/cregit-ec2" > /run/census-batch4-hold
echo "== hold set; finalize decide/hold test:"; systemctl is-active census-batch4-finalize.service
{ echo "== $(date -u +%FT%TZ) running projects when STOP was written"
  for k in 1 2 3; do echo "--- p$k"; $B/census-steps /b4p$k/ctp /home/ec2-user/batch4-input/manifest.batch4p$k.tsv --highlight '' | sed -n '4,20p' | cut -c1-110; done; } > $R
cat $R
for k in 1 2 3; do touch /b4p$k/ctp/STOP; chown ec2-user: /b4p$k/ctp/STOP; done; echo "STOP written $(date -u +%T)"
sudo -u ec2-user $B/census-batch4-live; aws s3 cp s3://${RUNNER_BUCKET}/batch4/live/progress.txt - | head -1
echo "== copy the build"
for k in 1 2 3; do
  D=/b4p$k/cregit-ec2
  [ -e $D ] && { echo "$D exists already"; continue; }
  tar -C /data -cf - --exclude='cregit-ec2/tokenizeByBlobId/build/*' cregit-ec2 | tar -C /b4p$k -xpf -
  mkdir -p $D/tokenizeByBlobId/build; chown ec2-user: $D $D/tokenizeByBlobId/build
  n_src=$(cd /data/cregit-ec2 && find . -path ./tokenizeByBlobId/build -prune -o -print | wc -l)
  n_dst=$(cd $D && find . -path ./tokenizeByBlobId/build -prune -o -print | wc -l)
  echo "p$k: entries src $n_src copy $n_dst; build/ entries $(ls -A $D/tokenizeByBlobId/build | wc -l); owner $(stat -c %U $D); $(sudo -u ec2-user git -C $D rev-parse --short HEAD) dirty=[$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no | wc -l)]"
done
echo "blobExec jar sums: $(for d in /data/cregit-ec2 /b4p1/cregit-ec2 /b4p2/cregit-ec2 /b4p3/cregit-ec2; do find $d -name '*.jar' -path '*blobExec*' -newer $d/README.md 2>/dev/null | head -1 | xargs -r sha256sum | cut -c1-12; done | tr '\n' ' ')"
echo "tree diff (excluding build/, .devenv): $(diff -rq --no-dereference -x build -x .devenv /data/cregit-ec2 /b4p1/cregit-ec2 2>&1 | wc -l) differences"
for k in 1 2 3; do
  cp -p /home/ec2-user/census-batch4p$k.cfg /home/ec2-user/census-batch4p$k.cfg.data-cregit 2>/dev/null
  printf '# ctp config (CTP_CONFIG) for census batch 4 part p%s on the batch 2 instance: cregit 95cdc88, a per-part copy\n# /b4p%s/cregit-ec2 (own tokenizeByBlobId/build temp dir, 2026-10-09 13:4x), output on loop XFS /b4p%s.\n[paths]\ncregit_dir = /b4p%s/cregit-ec2\noutput_dir = /b4p%s/census-2026-10-batch4\n' $k $k $k $k $k > /home/ec2-user/census-batch4p$k.cfg
  chown ec2-user: /home/ec2-user/census-batch4p$k.cfg
done
grep -h cregit_dir /home/ec2-user/census-batch4p*.cfg
echo "== identity check on /b4p1/cregit-ec2"
cat > /home/ec2-user/srcml-sha-b4.sh <<'U'
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cd /b4p1/cregit-ec2
devenv shell -- bash -c 'echo "SRCML_PREFIX=$SRCML_PREFIX"; sha256sum "$SRCML_PREFIX/lib/libsrcml.so.1.1.0"; command -v srcml'
U
cat > /home/ec2-user/check-b4c.sh <<'U'
set -uo pipefail
C=/b4p1/ctp-check2
[ -d $C ] || git clone -q /home/ec2-user/batch2-input/ctp.bundle $C -b feat/e2e-runner
cd $C; [ "$(git rev-parse --short HEAD)" = ca113e3 ] || { echo "wrong ctp HEAD"; exit 1; }
[ -x .venv/bin/python ] || { python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; }
printf '# libexpat check on the per-part cregit copy /b4p1/cregit-ec2 (scratch output).\n[paths]\ncregit_dir = /b4p1/cregit-ec2\noutput_dir = /b4p1/libexpat-check2/out\n' > /home/ec2-user/census-batch4-check2.cfg
export CTP_CONFIG=/home/ec2-user/census-batch4-check2.cfg
mkdir -p /b4p1/libexpat-check2/out
I=/home/ec2-user/batch2-input
.venv/bin/python ctp.py census --manifest $I/manifest.libexpat.tsv --project-meta $I/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10 > /data/logs/check-b4c.log 2>&1
echo "census rc=$?"; tail -1 /data/logs/check-b4c.log
U
chown ec2-user: /home/ec2-user/srcml-sha-b4.sh /home/ec2-user/check-b4c.sh
out=$(sudo -u ec2-user -i bash /home/ec2-user/srcml-sha-b4.sh 2>/dev/null | tail -3); echo "$out"
got_s=$(echo "$out" | grep -o '^[0-9a-f]\{64\}' | tail -1)
[ "$got_s" = "$WANT_SRCML" ] && echo "libsrcml OK" || echo "libsrcml DIFFERS ($got_s)"
t0=$(date +%s); sudo -u ec2-user -i bash /home/ec2-user/check-b4c.sh
got=$(sha256sum /b4p1/libexpat-check2/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet 2>/dev/null | cut -d' ' -f1)
echo "check took $(( $(date +%s) - t0 ))s; libexpat Parquet sha256 $got"
[ "$got" = "$WANT_PQ" ] && echo "CHECK OK" || echo "CHECK FAILED"
grep -o '"cregit_dir": "[^"]*"' /b4p1/ctp-check2/runs.log 2>/dev/null | tail -1
echo "tokdir in copy during check (should be 0 now): $(ls -A /b4p1/cregit-ec2/tokenizeByBlobId/build | wc -l)"
echo "== parts $(date -u +%T): $(systemctl is-active census-batch4p1.service census-batch4p2.service census-batch4p3.service | tr '\n' ' ')"
for k in 1 2 3; do grep '♥' /data/logs/batch4p$k.log | tail -1 | cut -c1-230; done
systemctl is-active census-batch2.service census-batch3L.service | tr '\n' ' '; echo
