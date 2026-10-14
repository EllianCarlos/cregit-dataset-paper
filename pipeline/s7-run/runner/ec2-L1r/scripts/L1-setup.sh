# L1-setup.sh (big EC2 ${RUNNER_EC2_BIG}): census L1r (batch 1 rerun, L: torvalds__linux and
# SAP__project-foxhound, user decision 2026-10-12 ~14:10 UTC), part 1: pre-checks, the loop XFS image
# /data/loop/bL1r.img (3000G sparse) at /bL1r, the inputs (s3://BUCKET/L1r/input/ to ~ec2-user/L1r-input/:
# manifest.L1r.tsv, project_meta.L1r.json, SHA256SUMS; built on the local machine by build-L1r-input.py),
# ctp clone (from /bL7b/ctp), cregit copy (from /data/cregit-ec2, 95cdc88; census-L1r-cregit checks it
# out at 57551d7 from the bundle), config, gate helper scripts. Made from the L23 L1-setup.sh
# (2026-10-11). Run it only after upload-L1r.sh printed ALL OK. Touches no running census: it only
# reads /bL7b and /data/cregit-ec2 (tar, git clone, cp).
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin
WANT_M=3443e70ac9d78ff3c428bfddc3fa311873f38b161b761637d41b69560f1e6768  # manifest.L1r.tsv
WANT_J=c4c5b946d8f8623d045ea6f0ac872b37ff9e2a5eb0fe12d0ece501329d52c081  # project_meta.L1r.json
echo "== pre $(date -u +%FT%TZ)"
[ "$(sha256sum $B/census-other-done | cut -c1-16)" = dfc799466c7e8068 ] || { echo "census-other-done is not the L23 version"; exit 1; }
[ "$(sha256sum $B/census-batch4-guard | cut -c1-16)" = 3aea045af99d1e36 ] || { echo "census-batch4-guard is not the L23 version"; exit 1; }
[ "$(sha256sum $B/census-backup | cut -c1-16)" = ba1a206a0227a8be ] || { echo "census-backup is not the L23 version"; exit 1; }
echo "MemAvailable $(awk '/MemAvailable/{printf "%.0f GiB", $2/1048576}' /proc/meminfo); /data free $(df -BG --output=avail /data | tail -1 | tr -d ' '); load $(cut -d' ' -f1-3 /proc/loadavg)"
echo "census-L7-20 / L7-20b / L22 / batch5L / L23-wait / L23: $(systemctl is-active census-L7-20.service census-L7-20b.service census-L22.service census-batch5L.service census-L23-wait.service census-L23.service | tr '\n' ' ')"
echo "== image"
img=/data/loop/bL1r.img; mp=/bL1r
[ -e $img ] || { truncate -s 3000G $img; mkfs.xfs -q -L bL1r $img; }
mkdir -p $mp
grep -q "^$img " /etc/fstab || echo "$img $mp xfs loop,noatime,discard,nofail,x-systemd.requires-mounts-for=/data 0 0" >> /etc/fstab
mountpoint -q $mp || mount $mp
chown ec2-user:ec2-user $mp
echo "$(findmnt -no TARGET,SOURCE,FSTYPE /bL1r) fsid=$(stat -f -c %i /bL1r) size=$(df -BG --output=size /bL1r | tail -1) | /bL7b fsid=$(stat -f -c %i /bL7b)"
echo "== inputs (s3://BUCKET/L1r/input/)"
sudo -u ec2-user bash -c "set -e; export AWS_PAGER=; mkdir -p ~/L1r-input; aws s3 cp s3://${RUNNER_BUCKET}/L1r/input/ ~/L1r-input/ --recursive --only-show-errors; cd ~/L1r-input; sha256sum --quiet -c SHA256SUMS; [ \"\$(sha256sum manifest.L1r.tsv | cut -d' ' -f1)\" = $WANT_M ]; [ \"\$(sha256sum project_meta.L1r.json | cut -d' ' -f1)\" = $WANT_J ]; echo \"L1r inputs: sha256 ok: \$(cut -c1-16,65- SHA256SUMS | tr '\n' ' ')\"" || { echo "L1R INPUTS MISSING OR BAD (has upload-L1r.sh printed ALL OK?)"; exit 1; }
[ "$(grep -v '^#' /home/ec2-user/L1r-input/manifest.L1r.tsv | cut -f1 | tr '\n' ' ')" = "SAP__project-foxhound torvalds__linux " ] && echo "rows: SAP__project-foxhound torvalds__linux (LPT)" || { echo "ROWS DIFFER"; exit 1; }
echo "== ctp clone (from /bL7b/ctp)"
sudo -u ec2-user bash -c 'set -e; C=/bL1r/ctp; [ -d $C ] || git clone -q /bL7b/ctp $C; cd $C; [ "$(git rev-parse --short HEAD)" = ca113e3 ]; [ -z "$(git status --porcelain --untracked-files=no)" ]; [ -x .venv/bin/python ] || cp -a /bL7b/ctp/.venv .venv; echo "$(git rev-parse HEAD) $(git branch --show-current) $(.venv/bin/python -c "import duckdb,sys;print(sys.version.split()[0], duckdb.__version__, sys.prefix)")"; mkdir -p /bL1r/census-2026-10-L1r' || { echo "ctp clone FAILED"; exit 1; }
echo "== cregit copy (from /data/cregit-ec2, 95cdc88: the bundle prerequisite)"
D=/bL1r/cregit-ec2
if [ ! -e $D ]; then
  # into a temp dir first, without the build dir (a census may write it while tar reads: the
  # 'file changed as we read it' race of 2026-10-10), then one mv into place
  CT=$(mktemp -d /bL1r/.cregit-copy.XXXX)
  tar -C /data -cf - --exclude='cregit-ec2/tokenizeByBlobId/build' cregit-ec2 | tar -C $CT -xpf - || { echo 'cregit copy FAILED'; exit 1; }
  mv $CT/cregit-ec2 $D && rmdir $CT
  mkdir -p $D/tokenizeByBlobId/build; chown ec2-user: $D $D/tokenizeByBlobId/build
fi
jar() { find $1 -name '*.jar' -path '*blobExec*' -newer $1/README.md 2>/dev/null | head -1 | xargs -r sha256sum | cut -c1-16; }
echo "copy: $(sudo -u ec2-user git -C $D rev-parse --short HEAD) dirty=[$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no | wc -l)] build/ entries $(ls -A $D/tokenizeByBlobId/build | wc -l) owner $(stat -c %U $D); jar $(jar $D) vs /data/cregit-ec2 $(jar /data/cregit-ec2); tree diff to /data/cregit-ec2 (no build/, .devenv): $(diff -rq --no-dereference -x build -x .devenv /data/cregit-ec2 $D 2>&1 | wc -l)"
printf '# ctp config (CTP_CONFIG) for census L1r on the big EC2: cregit 57551d7, own copy\n# /bL1r/cregit-ec2 (path fixed before the start), output on loop XFS /bL1r.\n[paths]\ncregit_dir = /bL1r/cregit-ec2\noutput_dir = /bL1r/census-2026-10-L1r\n' > /home/ec2-user/census-L1r.cfg
printf '# libexpat check on the cregit copy /bL1r/cregit-ec2 (scratch output).\n[paths]\ncregit_dir = /bL1r/cregit-ec2\noutput_dir = /bL1r/libexpat-check/out\n' > /home/ec2-user/census-L1r-check.cfg
chown ec2-user: /home/ec2-user/census-L1r.cfg /home/ec2-user/census-L1r-check.cfg
echo "== gate helper scripts"
cat > /home/ec2-user/srcml-sha-bL1r.sh <<'U'
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cd /bL1r/cregit-ec2
devenv shell -- bash -c 'sha256sum "$SRCML_PREFIX/lib/libsrcml.so.1.1.0"'
U
cat > /home/ec2-user/check-bL1r.sh <<'U'
set -uo pipefail
C=/bL1r/ctp-check
[ -d $C ] || git clone -q /bL7b/ctp $C
cd $C; [ "$(git rev-parse --short HEAD)" = ca113e3 ] || { echo "wrong ctp HEAD"; exit 1; }
[ -x .venv/bin/python ] || cp -a /bL7b/ctp/.venv .venv
export CTP_CONFIG=/home/ec2-user/census-L1r-check.cfg
mkdir -p /bL1r/libexpat-check/out
I=/home/ec2-user/batch2-input
.venv/bin/python ctp.py census --manifest $I/manifest.libexpat.tsv --project-meta $I/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10 > /data/logs/check-bL1r.log 2>&1
echo "census rc=$?"; tail -1 /data/logs/check-bL1r.log | cut -c1-200
U
chown ec2-user: /home/ec2-user/srcml-sha-bL1r.sh /home/ec2-user/check-bL1r.sh
echo "helper scripts written; the gate runs in census-L1r-cregit"
echo "census-L7-20 / L7-20b / L22 / batch5L / L23-wait / L23: $(systemctl is-active census-L7-20.service census-L7-20b.service census-L22.service census-batch5L.service census-L23-wait.service census-L23.service | tr '\n' ' ')"
