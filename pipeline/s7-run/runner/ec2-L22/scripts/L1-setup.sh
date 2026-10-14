# L1-setup.sh (batch 2 instance ${RUNNER_EC2_BIG}): census L22 (the 2 L projects of batch 22, gcc and emacs),
# part 1: pre-checks, the loop XFS image /data/loop/bL22.img (2000G sparse) at /bL22, inputs, ctp clone,
# cregit copy (path fixed: /bL22/cregit-ec2), config, identity check on the copy. Made from the batch6L
# L1-setup.sh (2026-10-10 ~00:25 UTC). The inputs may not be in S3 yet (the waiter copies them later);
# the identity gate runs in census-L22-cregit at the new commit. Touches no running census.
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin
WANT_SRCML=dea4467bb1b0a435e4536be13367325564b82e14ff69b478ad31bf144a8455f3
WANT_PQ=40511e0de1a285b5bbc4ae0ff277e4775c5d67709966dd7c64dc9163c638fc5d
echo "== pre $(date -u +%FT%TZ)"
[ "$(sha256sum $B/census-other-done | cut -c1-16)" = 5711f7113abbf1e5 ] || { echo "census-other-done is not the L7-20 version"; exit 1; }
[ "$(sha256sum $B/census-batch4-guard | cut -c1-16)" = 70a5a009ee0c9815 ] || { echo "census-batch4-guard is not the L7-20 version"; exit 1; }
[ "$(sha256sum $B/census-backup | cut -c1-16)" = f55939db56fb9208 ] || { echo "census-backup is not the L7-20 version"; exit 1; }
echo "MemAvailable $(awk '/MemAvailable/{printf "%.0f GiB", $2/1048576}' /proc/meminfo); /data free $(df -BG --output=avail /data | tail -1 | tr -d ' '); load $(cut -d' ' -f1-3 /proc/loadavg)"
echo "== image"
img=/data/loop/bL22.img; mp=/bL22
[ -e $img ] || { truncate -s 2000G $img; mkfs.xfs -q -L bL22 $img; }
mkdir -p $mp
grep -q "^$img " /etc/fstab || echo "$img $mp xfs loop,noatime,discard,nofail,x-systemd.requires-mounts-for=/data 0 0" >> /etc/fstab
mountpoint -q $mp || mount $mp
chown ec2-user:ec2-user $mp
echo "$(findmnt -no TARGET,SOURCE,FSTYPE /bL22) fsid=$(stat -f -c %i /bL22) size=$(df -BG --output=size /bL22 | tail -1) | /data fsid=$(stat -f -c %i /data) | b4p/b5L fsids: $(for k in /b4p1 /b4p2 /b4p3 /b5L; do stat -f -c %i $k; done | tr '\n' ' ')"
echo "== inputs"
sudo -u ec2-user bash -c 'export AWS_PAGER=""; mkdir -p ~/L22-input; aws s3 cp s3://${RUNNER_BUCKET}/batch22/input/ ~/L22-input/ --recursive --only-show-errors 2>/dev/null; cd ~/L22-input && sha256sum --quiet -c SHA256SUMS 2>/dev/null && echo "sha256 ok ($(grep -c . SHA256SUMS) files)" || echo "inputs not in S3 yet (the waiter copies them)"'
echo "== ctp clone"
sudo -u ec2-user bash -c 'set -e; C=/bL22/ctp; [ -d $C ] || git clone -q /home/ec2-user/batch2-input/ctp.bundle $C -b feat/e2e-runner; cd $C; [ "$(git rev-parse --short HEAD)" = ca113e3 ]; [ -x .venv/bin/python ] || { python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; }; echo "$(git rev-parse HEAD) $(.venv/bin/python -c "import duckdb,sys;print(sys.version.split()[0], duckdb.__version__)")"; mkdir -p /bL22/census-2026-10-L22' || exit 1
echo "== cregit copy"
D=/bL22/cregit-ec2
if [ ! -e $D ]; then
  # into a temp dir first, without the whole build dir (a census may write it while tar reads: the
  # 'file changed as we read it' race of 2026-10-10), then one mv into place
  CT=$(mktemp -d /bL22/.cregit-copy.XXXX)
  tar -C /data -cf - --exclude='cregit-ec2/tokenizeByBlobId/build' cregit-ec2 | tar -C $CT -xpf - || { echo 'cregit copy FAILED'; exit 1; }
  mv $CT/cregit-ec2 $D && rmdir $CT
  mkdir -p $D/tokenizeByBlobId/build; chown ec2-user: $D $D/tokenizeByBlobId/build
fi
jar() { find $1 -name '*.jar' -path '*blobExec*' -newer $1/README.md 2>/dev/null | head -1 | xargs -r sha256sum | cut -c1-16; }
echo "copy: $(sudo -u ec2-user git -C $D rev-parse --short HEAD) dirty=[$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no | wc -l)] build/ entries $(ls -A $D/tokenizeByBlobId/build | wc -l) owner $(stat -c %U $D); jar $(jar $D) vs /data/cregit-ec2 $(jar /data/cregit-ec2); tree diff (no build/, .devenv): $(diff -rq --no-dereference -x build -x .devenv /data/cregit-ec2 $D 2>&1 | wc -l)"
printf '# ctp config (CTP_CONFIG) for census L22 on the batch 2 instance: cregit 95cdc88, own copy\n# /bL22/cregit-ec2 (path fixed before the start), output on loop XFS /bL22.\n[paths]\ncregit_dir = /bL22/cregit-ec2\noutput_dir = /bL22/census-2026-10-L22\n' > /home/ec2-user/census-L22.cfg
printf '# libexpat check on the cregit copy /bL22/cregit-ec2 (scratch output).\n[paths]\ncregit_dir = /bL22/cregit-ec2\noutput_dir = /bL22/libexpat-check/out\n' > /home/ec2-user/census-L22-check.cfg
chown ec2-user: /home/ec2-user/census-L22.cfg /home/ec2-user/census-L22-check.cfg
echo "== identity check on /bL22/cregit-ec2"
cat > /home/ec2-user/srcml-sha-bL22.sh <<'U'
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cd /bL22/cregit-ec2
devenv shell -- bash -c 'sha256sum "$SRCML_PREFIX/lib/libsrcml.so.1.1.0"'
U
cat > /home/ec2-user/check-bL22.sh <<'U'
set -uo pipefail
C=/bL22/ctp-check
[ -d $C ] || git clone -q /home/ec2-user/batch2-input/ctp.bundle $C -b feat/e2e-runner
cd $C; [ "$(git rev-parse --short HEAD)" = ca113e3 ] || { echo "wrong ctp HEAD"; exit 1; }
[ -x .venv/bin/python ] || { python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; }
export CTP_CONFIG=/home/ec2-user/census-L22-check.cfg
mkdir -p /bL22/libexpat-check/out
I=/home/ec2-user/batch2-input
.venv/bin/python ctp.py census --manifest $I/manifest.libexpat.tsv --project-meta $I/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10 > /data/logs/check-bL22.log 2>&1
echo "census rc=$?"; tail -1 /data/logs/check-bL22.log | cut -c1-200
U
chown ec2-user: /home/ec2-user/srcml-sha-bL22.sh /home/ec2-user/check-bL22.sh
echo "helper scripts written; the gate runs in census-L22-cregit"
systemctl is-active census-batch2.service census-batch3L.service census-batch4p1.service census-batch4p2.service census-batch4p3.service census-batch5L.service census-batch6L.service census-L7-20.service | tr '\n' ' '; echo
