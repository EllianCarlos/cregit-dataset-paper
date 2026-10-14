# L1-setup.sh (big EC2 ${RUNNER_EC2_BIG}): census L7-20b (the 40 rows at the END of the L7-20 queue, from
# row 17 BrowserWorks__waterfox to row 56), part 1: pre-checks, the loop XFS image /data/loop/bL7b.img
# (3000G sparse) at /bL7b, the inputs (built here from the L7-20 inputs on this instance), ctp clone and
# cregit copy (both copied from the L7-20 ones), config, gate helper scripts. Made from the L22
# L1-setup.sh (2026-10-11). Touches no running census: it only reads /bL7 (tar, git clone, cp).
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin
SPLIT=BrowserWorks__waterfox; SPLITROW=17
WANT_M=58af4ad64115204e8d7ca912302e942cf40bb523ad1d99495d81967e01e21729
WANT_J=28ddbccc4ba973ff7b105e24f2b0a2e9399e829eddfc283caa0548d956ceb1a3
echo "== pre $(date -u +%FT%TZ)"
[ "$(sha256sum $B/census-other-done | cut -c1-16)" = 0acc488b9a1ed5c6 ] || { echo "census-other-done is not the L22 version"; exit 1; }
[ "$(sha256sum $B/census-batch4-guard | cut -c1-16)" = a96cab084a9525b2 ] || { echo "census-batch4-guard is not the L22 version"; exit 1; }
[ "$(sha256sum $B/census-backup | cut -c1-16)" = dc3065d425727ea8 ] || { echo "census-backup is not the L22 version"; exit 1; }
[ -e /bL7/ctp/STOP ] && { echo "/bL7/ctp/STOP exists already"; exit 1; }
echo "MemAvailable $(awk '/MemAvailable/{printf "%.0f GiB", $2/1048576}' /proc/meminfo); /data free $(df -BG --output=avail /data | tail -1 | tr -d ' '); load $(cut -d' ' -f1-3 /proc/loadavg)"
echo "census-L7-20: $(systemctl is-active census-L7-20.service), counts $($B/census-steps --counts /bL7/ctp /home/ec2-user/L7-20-input/manifest.L7-20.tsv); state dirs: $(ls /bL7/ctp/state | tr '\n' ' ')"
echo "== image"
img=/data/loop/bL7b.img; mp=/bL7b
[ -e $img ] || { truncate -s 3000G $img; mkfs.xfs -q -L bL7b $img; }
mkdir -p $mp
grep -q "^$img " /etc/fstab || echo "$img $mp xfs loop,noatime,discard,nofail,x-systemd.requires-mounts-for=/data 0 0" >> /etc/fstab
mountpoint -q $mp || mount $mp
chown ec2-user:ec2-user $mp
echo "$(findmnt -no TARGET,SOURCE,FSTYPE /bL7b) fsid=$(stat -f -c %i /bL7b) size=$(df -BG --output=size /bL7b | tail -1) | /bL7 fsid=$(stat -f -c %i /bL7)"
echo "== inputs (built from ~ec2-user/L7-20-input; nothing from S3)"
cat > /home/ec2-user/build-L7-20b-input.py <<'PY'
"""Build ~/L7-20b-input from ~/L7-20-input: the manifest rows from SPLIT (row SPLITROW) to the end,
unchanged and in the same order, with a new header; the sidecar copied byte for byte.
Refuses if the inputs differ from the expected sha256 or if census L7-20 has started a split row."""
import hashlib, os, re, sys
src, dst, split, splitrow, want_m, want_j = sys.argv[1:7]
splitrow = int(splitrow)
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
m, j = os.path.join(src, "manifest.L7-20.tsv"), os.path.join(src, "project_meta.L7-20.json")
assert sha(m) == want_m, "L7-20 manifest sha256 differs"
assert sha(j) == want_j, "L7-20 sidecar sha256 differs"
lines = open(m, "rb").read().decode("utf-8").splitlines(keepends=True)
pred = [re.match(r"^#\s+(\d+\.\d)\s+(batch\d+)\s+(\S+)\s*$", l) for l in lines]
pred = [(float(x[1]), x[2], x[3]) for x in pred if x]
cols = [l for l in lines if l.startswith("# Columns:")]
data = [l for l in lines if l.strip() and not l.startswith("#")]
names = [l.split("\t", 1)[0] for l in data]
assert len(cols) == 1 and len(data) == 56 and [p[2] for p in pred] == names, "manifest layout differs"
assert names[splitrow - 1] == split, f"row {splitrow} is {names[splitrow - 1]}, not {split}"
started = set(os.listdir("/bL7/ctp/state"))
take = names[splitrow - 1:]
bad = sorted(started & set(take))
assert not bad, f"census L7-20 has started split rows: {bad}"
hours = sum(p[0] for p in pred[splitrow - 1:])
keep = sum(p[0] for p in pred[:splitrow - 1] if p[2] not in started)
os.makedirs(dst, exist_ok=True)
hdr = [f"# Census L7-20b on the big EC2: rows {splitrow}-56 of the L7-20 v2 manifest (sha256 {want_m[:16]}),\n",
       f"# unchanged and in the same order (longest predicted first). Census L7-20 stops before row {splitrow}\n",
       f"# ({split}): census-L7-20-split writes /bL7/ctp/STOP when it has started every earlier row.\n",
       f"# {len(take)} projects, {hours:.1f} h predicted (inferred). Predicted hours, batch, name, in row order:\n"]
hdr += [f"#   {h:6.1f}  {b}  {n}\n" for h, b, n in pred[splitrow - 1:]]
out = "".join(hdr) + cols[0] + "".join(data[splitrow - 1:])
open(os.path.join(dst, "manifest.L7-20b.tsv"), "w", encoding="utf-8").write(out)
open(os.path.join(dst, "project_meta.L7-20b.json"), "wb").write(open(j, "rb").read())
print(f"L7-20b: {len(take)} rows ({take[0]} .. {take[-1]}), {hours:.1f} h predicted; "
      f"L7-20 keeps {splitrow - 1 - len(started & set(names[:splitrow - 1]))} not-started rows "
      f"({keep:.1f} h) and {len(started)} started")
PY
chown ec2-user: /home/ec2-user/build-L7-20b-input.py
sudo -u ec2-user bash -c "set -e; mkdir -p ~/L7-20b-input; cd ~; python3 -I build-L7-20b-input.py ~/L7-20-input ~/L7-20b-input $SPLIT $SPLITROW $WANT_M $WANT_J; cd ~/L7-20b-input; sha256sum manifest.L7-20b.tsv project_meta.L7-20b.json > SHA256SUMS; sha256sum --quiet -c SHA256SUMS && echo \"sha256 ok: \$(cut -c1-16,65- SHA256SUMS | tr '\n' ' ')\"" || { echo "INPUT BUILD FAILED"; exit 1; }
diff <(grep -v '^#' /home/ec2-user/L7-20-input/manifest.L7-20.tsv | tail -n 40) <(grep -v '^#' /home/ec2-user/L7-20b-input/manifest.L7-20b.tsv) > /dev/null && echo "data rows identical to the last 40 rows of L7-20" || { echo "ROWS DIFFER"; exit 1; }
echo "== ctp clone (from /bL7/ctp)"
sudo -u ec2-user bash -c 'set -e; C=/bL7b/ctp; [ -d $C ] || git clone -q /bL7/ctp $C; cd $C; [ "$(git rev-parse --short HEAD)" = ca113e3 ]; [ -z "$(git status --porcelain --untracked-files=no)" ]; [ -x .venv/bin/python ] || cp -a /bL7/ctp/.venv .venv; echo "$(git rev-parse HEAD) $(git branch --show-current) $(.venv/bin/python -c "import duckdb,sys;print(sys.version.split()[0], duckdb.__version__, sys.prefix)")"; mkdir -p /bL7b/census-2026-10-L7-20b' || { echo "ctp clone FAILED"; exit 1; }
echo "== cregit copy (from /bL7/cregit-ec2)"
D=/bL7b/cregit-ec2
if [ ! -e $D ]; then
  # into a temp dir first, without the build dir (a census may write it while tar reads: the
  # 'file changed as we read it' race of 2026-10-10), then one mv into place
  CT=$(mktemp -d /bL7b/.cregit-copy.XXXX)
  tar -C /bL7 -cf - --exclude='cregit-ec2/tokenizeByBlobId/build' cregit-ec2 | tar -C $CT -xpf - || { echo 'cregit copy FAILED'; exit 1; }
  mv $CT/cregit-ec2 $D && rmdir $CT
  mkdir -p $D/tokenizeByBlobId/build; chown ec2-user: $D $D/tokenizeByBlobId/build
fi
jar() { find $1 -name '*.jar' -path '*blobExec*' -newer $1/README.md 2>/dev/null | head -1 | xargs -r sha256sum | cut -c1-16; }
echo "copy: $(sudo -u ec2-user git -C $D rev-parse --short HEAD) dirty=[$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no | wc -l)] build/ entries $(ls -A $D/tokenizeByBlobId/build | wc -l) owner $(stat -c %U $D); jar $(jar $D) vs /data/cregit-ec2 $(jar /data/cregit-ec2); tree diff to /bL7/cregit-ec2 (no build/, .devenv): $(diff -rq --no-dereference -x build -x .devenv /bL7/cregit-ec2 $D 2>&1 | wc -l)"
printf '# ctp config (CTP_CONFIG) for census L7-20b on the big EC2: cregit 1f17663, own copy\n# /bL7b/cregit-ec2 (path fixed before the start), output on loop XFS /bL7b.\n[paths]\ncregit_dir = /bL7b/cregit-ec2\noutput_dir = /bL7b/census-2026-10-L7-20b\n' > /home/ec2-user/census-L7-20b.cfg
printf '# libexpat check on the cregit copy /bL7b/cregit-ec2 (scratch output).\n[paths]\ncregit_dir = /bL7b/cregit-ec2\noutput_dir = /bL7b/libexpat-check/out\n' > /home/ec2-user/census-L7-20b-check.cfg
chown ec2-user: /home/ec2-user/census-L7-20b.cfg /home/ec2-user/census-L7-20b-check.cfg
echo "== gate helper scripts"
cat > /home/ec2-user/srcml-sha-bL7b.sh <<'U'
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cd /bL7b/cregit-ec2
devenv shell -- bash -c 'sha256sum "$SRCML_PREFIX/lib/libsrcml.so.1.1.0"'
U
cat > /home/ec2-user/check-bL7b.sh <<'U'
set -uo pipefail
C=/bL7b/ctp-check
[ -d $C ] || git clone -q /bL7/ctp $C
cd $C; [ "$(git rev-parse --short HEAD)" = ca113e3 ] || { echo "wrong ctp HEAD"; exit 1; }
[ -x .venv/bin/python ] || cp -a /bL7/ctp/.venv .venv
export CTP_CONFIG=/home/ec2-user/census-L7-20b-check.cfg
mkdir -p /bL7b/libexpat-check/out
I=/home/ec2-user/batch2-input
.venv/bin/python ctp.py census --manifest $I/manifest.libexpat.tsv --project-meta $I/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10 > /data/logs/check-bL7b.log 2>&1
echo "census rc=$?"; tail -1 /data/logs/check-bL7b.log | cut -c1-200
U
chown ec2-user: /home/ec2-user/srcml-sha-bL7b.sh /home/ec2-user/check-bL7b.sh
echo "helper scripts written; the gate runs in census-L7-20b-cregit"
echo "census-L7-20 / L22 / batch5L: $(systemctl is-active census-L7-20.service census-L22.service census-batch5L.service | tr '\n' ' '); /bL7/ctp/STOP: $([ -e /bL7/ctp/STOP ] && echo present || echo absent)"
