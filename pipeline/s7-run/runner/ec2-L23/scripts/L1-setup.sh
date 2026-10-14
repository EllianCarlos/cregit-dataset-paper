# L1-setup.sh (big EC2 ${RUNNER_EC2_BIG}): census L23 (the 8 L projects of batch 23, the DP8L v4
# near-miss supplement, ${RUNNER_STUDY_REPO} s7-run), part 1: pre-checks, the loop XFS image /data/loop/bL23.img
# (3000G sparse) at /bL23, the inputs (s3://BUCKET/batch23/input/ to ~ec2-user/batch23-input/, then
# build-L23-input.py writes ~ec2-user/L23-input/: manifest.L23.tsv in LPT order and project_meta.L23.json),
# ctp clone (from /bL7b/ctp), cregit copy (from /data/cregit-ec2, 95cdc88; census-L23-cregit checks it
# out at 57551d7 from the bundle), config, gate helper scripts. Made from the L7-20b L1-setup.sh
# (2026-10-11). Run it only after upload-batch23.sh printed ALL OK. Touches no running census: it only
# reads /bL7b and /data/cregit-ec2 (tar, git clone, cp).
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin
WANT_OUT=98152b6bd84ba2446cb90a6e30172c422d705a5a5c41f21b04e8b58791c7c043
echo "== pre $(date -u +%FT%TZ)"
[ "$(sha256sum $B/census-other-done | cut -c1-16)" = db590d92ef4633cb ] || { echo "census-other-done is not the L7-20b version"; exit 1; }
[ "$(sha256sum $B/census-batch4-guard | cut -c1-16)" = dfa4f57987280343 ] || { echo "census-batch4-guard is not the L7-20b version"; exit 1; }
[ "$(sha256sum $B/census-backup | cut -c1-16)" = 4787a2dd27c9271b ] || { echo "census-backup is not the L7-20b version"; exit 1; }
echo "MemAvailable $(awk '/MemAvailable/{printf "%.0f GiB", $2/1048576}' /proc/meminfo); /data free $(df -BG --output=avail /data | tail -1 | tr -d ' '); load $(cut -d' ' -f1-3 /proc/loadavg)"
echo "census-L7-20 / L7-20b / L22 / batch5L: $(systemctl is-active census-L7-20.service census-L7-20b.service census-L22.service census-batch5L.service | tr '\n' ' ')"
echo "== image"
img=/data/loop/bL23.img; mp=/bL23
[ -e $img ] || { truncate -s 3000G $img; mkfs.xfs -q -L bL23 $img; }
mkdir -p $mp
grep -q "^$img " /etc/fstab || echo "$img $mp xfs loop,noatime,discard,nofail,x-systemd.requires-mounts-for=/data 0 0" >> /etc/fstab
mountpoint -q $mp || mount $mp
chown ec2-user:ec2-user $mp
echo "$(findmnt -no TARGET,SOURCE,FSTYPE /bL23) fsid=$(stat -f -c %i /bL23) size=$(df -BG --output=size /bL23 | tail -1) | /bL7b fsid=$(stat -f -c %i /bL7b)"
echo "== inputs (s3://BUCKET/batch23/input/, then build-L23-input.py)"
cat > /home/ec2-user/build-L23-input.py <<'PY'
"""build-L23-input.py SRC DST: build DST/manifest.L23.tsv and DST/project_meta.L23.json from the batch 23
inputs in SRC (s3://BUCKET/batch23/input/, ${RUNNER_STUDY_REPO} s7-run). The manifest holds the 8 rows of
manifest.batch23L.tsv, unchanged, longest predicted first (LPT, the rule of census L7-20; ctp census starts
the rows in manifest order). The sidecar is a byte copy of project_meta.batch23L.json. Refuses if an input
or the output differs from the expected sha256. Predicted hours: split_batchN.py 23 (the fit of
split_batch5.py; inferred, weak for L projects)."""
import hashlib
import os
import sys

WANT_M = "c8c986af2a7667bb22010c2f71f90df1321e16795eb4ec5b52893eada7553ade"  # manifest.batch23L.tsv
WANT_J = "e823a93bc254428b945fa5b004bda4f341a78992107f7187fd1776b47ca1cb97"  # project_meta.batch23L.json
LPT = [("NetBSD__src", 17.5), ("openbsd__src", 12.3), ("checkedc__checkedc-clang", 10.6), ("WebKit__WebKit", 10.4),
       ("Xilinx__hls-llvm-project", 6.5), ("openbsd__ports", 0.5), ("alpinelinux__aports", 0.3),
       ("archlinuxcn__repo", 0.2)]
WANT_OUT = sys.argv[3] if len(sys.argv) > 3 else None


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main(src, dst):
    m = open(os.path.join(src, "manifest.batch23L.tsv"), "rb").read()
    j = open(os.path.join(src, "project_meta.batch23L.json"), "rb").read()
    assert sha(m) == WANT_M, "manifest.batch23L.tsv sha256 differs"
    assert sha(j) == WANT_J, "project_meta.batch23L.json sha256 differs"
    rows = {l.split("\t")[0]: l for l in m.decode("utf-8").splitlines(keepends=True)
            if l.strip() and not l.startswith("#")}
    assert sorted(rows) == sorted(n for n, _ in LPT), "the L rows differ from the LPT list"
    head = [f"# Census L23 (2026-10-11): the {len(LPT)} rows of manifest.batch23L.tsv (sha256 {WANT_M}),\n",
            "# unchanged, longest predicted first (LPT). Predicted hours (inferred):"
            + "".join(f" {n} {h}" for n, h in LPT) + "\n",
            "# Columns: name  url  category  file_filter  size_class  commit\n"]
    out = ("".join(head) + "".join(rows[n] for n, _ in LPT)).encode("utf-8")
    if WANT_OUT:
        assert sha(out) == WANT_OUT, f"manifest.L23.tsv sha256 {sha(out)} differs from {WANT_OUT}"
    os.makedirs(dst, exist_ok=True)
    open(os.path.join(dst, "manifest.L23.tsv"), "wb").write(out)
    open(os.path.join(dst, "project_meta.L23.json"), "wb").write(j)
    print(f"L23: {len(LPT)} rows, {sum(h for _, h in LPT):.1f} h predicted; manifest.L23.tsv sha256 {sha(out)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
PY
chown ec2-user: /home/ec2-user/build-L23-input.py
sudo -u ec2-user bash -c "set -e; export AWS_PAGER=; mkdir -p ~/batch23-input; aws s3 cp s3://${RUNNER_BUCKET}/batch23/input/ ~/batch23-input/ --recursive --only-show-errors; cd ~/batch23-input; sha256sum --quiet -c SHA256SUMS; echo \"batch23 inputs: sha256 ok (\$(grep -c . SHA256SUMS) files)\"" || { echo "BATCH 23 INPUTS MISSING OR BAD (has upload-batch23.sh printed ALL OK?)"; exit 1; }
sudo -u ec2-user bash -c "set -e; cd ~; python3 -I build-L23-input.py ~/batch23-input ~/L23-input $WANT_OUT; cd ~/L23-input; sha256sum manifest.L23.tsv project_meta.L23.json > SHA256SUMS; sha256sum --quiet -c SHA256SUMS && echo \"sha256 ok: \$(cut -c1-16,65- SHA256SUMS | tr '\n' ' ')\"" || { echo "INPUT BUILD FAILED"; exit 1; }
diff <(grep -v '^#' /home/ec2-user/batch23-input/manifest.batch23L.tsv | sort) <(grep -v '^#' /home/ec2-user/L23-input/manifest.L23.tsv | sort) > /dev/null && echo "data rows identical to manifest.batch23L.tsv (order: LPT)" || { echo "ROWS DIFFER"; exit 1; }
echo "== ctp clone (from /bL7b/ctp)"
sudo -u ec2-user bash -c 'set -e; C=/bL23/ctp; [ -d $C ] || git clone -q /bL7b/ctp $C; cd $C; [ "$(git rev-parse --short HEAD)" = ca113e3 ]; [ -z "$(git status --porcelain --untracked-files=no)" ]; [ -x .venv/bin/python ] || cp -a /bL7b/ctp/.venv .venv; echo "$(git rev-parse HEAD) $(git branch --show-current) $(.venv/bin/python -c "import duckdb,sys;print(sys.version.split()[0], duckdb.__version__, sys.prefix)")"; mkdir -p /bL23/census-2026-10-L23' || { echo "ctp clone FAILED"; exit 1; }
echo "== cregit copy (from /data/cregit-ec2, 95cdc88: the bundle prerequisite)"
D=/bL23/cregit-ec2
if [ ! -e $D ]; then
  # into a temp dir first, without the build dir (a census may write it while tar reads: the
  # 'file changed as we read it' race of 2026-10-10), then one mv into place
  CT=$(mktemp -d /bL23/.cregit-copy.XXXX)
  tar -C /data -cf - --exclude='cregit-ec2/tokenizeByBlobId/build' cregit-ec2 | tar -C $CT -xpf - || { echo 'cregit copy FAILED'; exit 1; }
  mv $CT/cregit-ec2 $D && rmdir $CT
  mkdir -p $D/tokenizeByBlobId/build; chown ec2-user: $D $D/tokenizeByBlobId/build
fi
jar() { find $1 -name '*.jar' -path '*blobExec*' -newer $1/README.md 2>/dev/null | head -1 | xargs -r sha256sum | cut -c1-16; }
echo "copy: $(sudo -u ec2-user git -C $D rev-parse --short HEAD) dirty=[$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no | wc -l)] build/ entries $(ls -A $D/tokenizeByBlobId/build | wc -l) owner $(stat -c %U $D); jar $(jar $D) vs /data/cregit-ec2 $(jar /data/cregit-ec2); tree diff to /data/cregit-ec2 (no build/, .devenv): $(diff -rq --no-dereference -x build -x .devenv /data/cregit-ec2 $D 2>&1 | wc -l)"
printf '# ctp config (CTP_CONFIG) for census L23 on the big EC2: cregit 57551d7, own copy\n# /bL23/cregit-ec2 (path fixed before the start), output on loop XFS /bL23.\n[paths]\ncregit_dir = /bL23/cregit-ec2\noutput_dir = /bL23/census-2026-10-L23\n' > /home/ec2-user/census-L23.cfg
printf '# libexpat check on the cregit copy /bL23/cregit-ec2 (scratch output).\n[paths]\ncregit_dir = /bL23/cregit-ec2\noutput_dir = /bL23/libexpat-check/out\n' > /home/ec2-user/census-L23-check.cfg
chown ec2-user: /home/ec2-user/census-L23.cfg /home/ec2-user/census-L23-check.cfg
echo "== gate helper scripts"
cat > /home/ec2-user/srcml-sha-bL23.sh <<'U'
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cd /bL23/cregit-ec2
devenv shell -- bash -c 'sha256sum "$SRCML_PREFIX/lib/libsrcml.so.1.1.0"'
U
cat > /home/ec2-user/check-bL23.sh <<'U'
set -uo pipefail
C=/bL23/ctp-check
[ -d $C ] || git clone -q /bL7b/ctp $C
cd $C; [ "$(git rev-parse --short HEAD)" = ca113e3 ] || { echo "wrong ctp HEAD"; exit 1; }
[ -x .venv/bin/python ] || cp -a /bL7b/ctp/.venv .venv
export CTP_CONFIG=/home/ec2-user/census-L23-check.cfg
mkdir -p /bL23/libexpat-check/out
I=/home/ec2-user/batch2-input
.venv/bin/python ctp.py census --manifest $I/manifest.libexpat.tsv --project-meta $I/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10 > /data/logs/check-bL23.log 2>&1
echo "census rc=$?"; tail -1 /data/logs/check-bL23.log | cut -c1-200
U
chown ec2-user: /home/ec2-user/srcml-sha-bL23.sh /home/ec2-user/check-bL23.sh
echo "helper scripts written; the gate runs in census-L23-cregit"
echo "census-L7-20 / L7-20b / L22 / batch5L: $(systemctl is-active census-L7-20.service census-L7-20b.service census-L22.service census-batch5L.service | tr '\n' ' ')"
