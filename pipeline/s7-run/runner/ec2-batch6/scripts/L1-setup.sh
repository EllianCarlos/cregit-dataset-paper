# L1-setup.sh (batch 2 instance ${RUNNER_EC2_BIG}): census batch6L (the 3 L projects of batch 6),
# part 1: pre-checks, the loop XFS image /data/loop/b6L.img (2000G sparse) at /b6L, inputs, ctp clone,
# cregit copy (path fixed: /b6L/cregit-ec2), config, identity check on the copy. Made from the batch5L
# L1-setup.sh (2026-10-09 ~20:00 UTC). Touches no running census.
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin
WANT_SRCML=dea4467bb1b0a435e4536be13367325564b82e14ff69b478ad31bf144a8455f3
WANT_PQ=40511e0de1a285b5bbc4ae0ff277e4775c5d67709966dd7c64dc9163c638fc5d
echo "== pre $(date -u +%FT%TZ)"
[ "$(sha256sum $B/census-other-done | cut -c1-16)" = bf852463a1fbb5ff ] || { echo "census-other-done is not the batch5L version"; exit 1; }
[ "$(sha256sum $B/census-batch4-guard | cut -c1-16)" = da30580a956ae1b3 ] || { echo "census-batch4-guard is not the batch5L version"; exit 1; }
[ "$(sha256sum $B/census-backup | cut -c1-16)" = 847c6c13d0ab8316 ] || { echo "census-backup is not the known version"; exit 1; }
echo "MemAvailable $(awk '/MemAvailable/{printf "%.0f GiB", $2/1048576}' /proc/meminfo); /data free $(df -BG --output=avail /data | tail -1 | tr -d ' '); load $(cut -d' ' -f1-3 /proc/loadavg)"
echo "== image"
img=/data/loop/b6L.img; mp=/b6L
[ -e $img ] || { truncate -s 2000G $img; mkfs.xfs -q -L b6L $img; }
mkdir -p $mp
grep -q "^$img " /etc/fstab || echo "$img $mp xfs loop,noatime,discard,nofail,x-systemd.requires-mounts-for=/data 0 0" >> /etc/fstab
mountpoint -q $mp || mount $mp
chown ec2-user:ec2-user $mp
echo "$(findmnt -no TARGET,SOURCE,FSTYPE /b6L) fsid=$(stat -f -c %i /b6L) size=$(df -BG --output=size /b6L | tail -1) | /data fsid=$(stat -f -c %i /data) | b4p/b5L fsids: $(for k in /b4p1 /b4p2 /b4p3 /b5L; do stat -f -c %i $k; done | tr '\n' ' ')"
echo "== inputs"
sudo -u ec2-user bash -c 'set -e; export AWS_PAGER=""; mkdir -p ~/batch6-input; aws s3 cp s3://${RUNNER_BUCKET}/batch6/input/ ~/batch6-input/ --recursive --only-show-errors; cd ~/batch6-input && sha256sum --quiet -c SHA256SUMS && echo "sha256 ok ($(grep -c . SHA256SUMS) files)"' || exit 1
echo "== ctp clone"
sudo -u ec2-user bash -c 'set -e; C=/b6L/ctp; [ -d $C ] || git clone -q /home/ec2-user/batch2-input/ctp.bundle $C -b feat/e2e-runner; cd $C; [ "$(git rev-parse --short HEAD)" = ca113e3 ]; [ -x .venv/bin/python ] || { python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; }; echo "$(git rev-parse HEAD) $(.venv/bin/python -c "import duckdb,sys;print(sys.version.split()[0], duckdb.__version__)")"; mkdir -p /b6L/census-2026-10-batch6L' || exit 1
echo "== cregit copy"
D=/b6L/cregit-ec2
if [ ! -e $D ]; then
  tar -C /data -cf - --exclude='cregit-ec2/tokenizeByBlobId/build/*' cregit-ec2 | tar -C /b6L -xpf -
  mkdir -p $D/tokenizeByBlobId/build; chown ec2-user: $D $D/tokenizeByBlobId/build
fi
jar() { find $1 -name '*.jar' -path '*blobExec*' -newer $1/README.md 2>/dev/null | head -1 | xargs -r sha256sum | cut -c1-16; }
echo "copy: $(sudo -u ec2-user git -C $D rev-parse --short HEAD) dirty=[$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no | wc -l)] build/ entries $(ls -A $D/tokenizeByBlobId/build | wc -l) owner $(stat -c %U $D); jar $(jar $D) vs /data/cregit-ec2 $(jar /data/cregit-ec2); tree diff (no build/, .devenv): $(diff -rq --no-dereference -x build -x .devenv /data/cregit-ec2 $D 2>&1 | wc -l)"
printf '# ctp config (CTP_CONFIG) for census batch6L on the batch 2 instance: cregit 95cdc88, own copy\n# /b6L/cregit-ec2 (path fixed before the start), output on loop XFS /b6L.\n[paths]\ncregit_dir = /b6L/cregit-ec2\noutput_dir = /b6L/census-2026-10-batch6L\n' > /home/ec2-user/census-batch6L.cfg
printf '# libexpat check on the cregit copy /b6L/cregit-ec2 (scratch output).\n[paths]\ncregit_dir = /b6L/cregit-ec2\noutput_dir = /b6L/libexpat-check/out\n' > /home/ec2-user/census-batch6L-check.cfg
chown ec2-user: /home/ec2-user/census-batch6L.cfg /home/ec2-user/census-batch6L-check.cfg
echo "== identity check on /b6L/cregit-ec2"
cat > /home/ec2-user/srcml-sha-b6L.sh <<'U'
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cd /b6L/cregit-ec2
devenv shell -- bash -c 'sha256sum "$SRCML_PREFIX/lib/libsrcml.so.1.1.0"'
U
cat > /home/ec2-user/check-b6L.sh <<'U'
set -uo pipefail
C=/b6L/ctp-check
[ -d $C ] || git clone -q /home/ec2-user/batch2-input/ctp.bundle $C -b feat/e2e-runner
cd $C; [ "$(git rev-parse --short HEAD)" = ca113e3 ] || { echo "wrong ctp HEAD"; exit 1; }
[ -x .venv/bin/python ] || { python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; }
export CTP_CONFIG=/home/ec2-user/census-batch6L-check.cfg
mkdir -p /b6L/libexpat-check/out
I=/home/ec2-user/batch2-input
.venv/bin/python ctp.py census --manifest $I/manifest.libexpat.tsv --project-meta $I/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10 > /data/logs/check-b6L.log 2>&1
echo "census rc=$?"; tail -1 /data/logs/check-b6L.log | cut -c1-200
U
chown ec2-user: /home/ec2-user/srcml-sha-b6L.sh /home/ec2-user/check-b6L.sh
got_s=$(sudo -u ec2-user -i bash /home/ec2-user/srcml-sha-b6L.sh 2>/dev/null | grep -o '^[0-9a-f]\{64\}' | tail -1)
[ "$got_s" = "$WANT_SRCML" ] && echo "libsrcml OK ($got_s)" || { echo "libsrcml DIFFERS ($got_s)"; exit 1; }
t0=$(date +%s); sudo -u ec2-user -i bash /home/ec2-user/check-b6L.sh
got=$(sha256sum /b6L/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet 2>/dev/null | cut -d' ' -f1)
ref=$(jar /data/cregit-ec2); [ "$(jar $D)" = "$ref" ] && echo "blobExec jar $ref equal" || { echo "CHECK FAILED: blobExec jar differs"; exit 1; }
echo "check took $(( $(date +%s) - t0 ))s; libexpat Parquet sha256 $got; $(grep -o '"cregit_dir": "[^"]*"' /b6L/ctp-check/runs.log 2>/dev/null | tail -1)"
[ "$got" = "$WANT_PQ" ] && echo "CHECK OK" || echo "CHECK FAILED"
systemctl is-active census-batch2.service census-batch3L.service census-batch4p1.service census-batch4p2.service census-batch4p3.service census-batch5L.service | tr '\n' ' '; echo
