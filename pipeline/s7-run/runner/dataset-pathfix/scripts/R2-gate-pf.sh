#!/usr/bin/env bash
# R2-gate-pf.sh (the path-fix instance, root, through ssm-run-pf.sh, after R1-setup-pf.sh): the
# identity gate of every part's own cregit copy. Copy of ~/s3-work/dataset-x1k/scripts/R2-gate.sh
# with CREGIT_COMMIT = 14b8db4 (the path-quoting fix) and 2 parts (/data1/pf, /data2/pf):
#   - libsrcml.so.1.1.0 sha256 through the copy's own devenv shell = dea4467b... (WANT_SRCML of v1);
#   - the libexpat Parquet sha256 with a scratch ctp clone /dataK/pf/ctp-check (ca113e3, the
#     unpatched v1 code, full steps with the firm step) and scratch output
#     /dataK/pf/libexpat-check/out, flags of the v1 check = 14eb5d72... (WANT_PQ of the v1 batches
#     7-26; unchanged by the fix: proven locally 2026-10-20, gate-pathfix/lpf2.gate.log);
#   - the blobExec jar sha256 = that of /data/cregit-ec2.
# Result: /etc/dataset-pathfix/pK.check, last line "CHECK OK ..." or "CHECK FAILED: ..."; exit 0
# only if both are OK. A rerun moves an earlier scratch clone and output aside (no delete).
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_LONG_A4}|${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_X1K_A}) echo "ABORT: $IID is on the refuse list"; exit 1 ;; esac
E=/etc/dataset-pathfix
NPARTS=2
CREGIT_COMMIT=14b8db468e4f6565fab5692a1ab1c3066d12f371
WANT_SRCML=dea4467bb1b0a435e4536be13367325564b82e14ff69b478ad31bf144a8455f3
WANT_PQ=14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
jar() { find $1 -name '*.jar' -path '*blobExec*' -newer $1/README.md 2>/dev/null | head -1 | xargs -r sha256sum | cut -c1-16; }
gate() {
  local K=$1 P=/data$1/pf R=$E/p$1.check D=/data$1/pf/cregit-ec2
  fail() { echo "CHECK FAILED: $*" | tee -a $R; return 1; }
  echo "check of $D started $(date -u +%FT%TZ)" > $R; chmod 644 $R
  [ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" = $CREGIT_COMMIT ] || { fail "$D is not at $CREGIT_COMMIT"; return 1; }
  printf '# libexpat check on the cregit copy %s (scratch output).\n[paths]\ncregit_dir = %s\noutput_dir = %s\n' $D $D $P/libexpat-check/out > $E/p$K.check.cfg
  chmod 644 $E/p$K.check.cfg
  cat > /home/ec2-user/pf-srcml-p$K.sh <<U
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cd $D
devenv shell -- bash -c 'sha256sum "\$SRCML_PREFIX/lib/libsrcml.so.1.1.0"'
U
  cat > /home/ec2-user/pf-check-p$K.sh <<U
set -uo pipefail
C=$P/ctp-check
[ -d \$C ] && mv \$C \$C.old.\$(date +%s)
git clone -q /data/input/ctp.bundle \$C -b feat/e2e-runner
cd \$C; [ "\$(git rev-parse --short HEAD)" = ca113e3 ] || { echo "wrong ctp HEAD"; exit 1; }
ln -s $P/ctp/.venv .venv
export CTP_CONFIG=$E/p$K.check.cfg
[ -d $P/libexpat-check/out ] && mv $P/libexpat-check/out $P/libexpat-check/out.old.\$(date +%s)
mkdir -p $P/libexpat-check/out
.venv/bin/python ctp.py census --manifest /data/input/manifest.libexpat.tsv --project-meta /data/input/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10 > $P/logs/check.log 2>&1
echo "census rc=\$?"
U
  chown ec2-user: /home/ec2-user/pf-srcml-p$K.sh /home/ec2-user/pf-check-p$K.sh
  local got_s got t0
  got_s=$(sudo -u ec2-user -i bash /home/ec2-user/pf-srcml-p$K.sh 2>/dev/null | grep -o '^[0-9a-f]\{64\}' | tail -1)
  echo "libsrcml.so.1.1.0 sha256 $got_s (copy $D)" | tee -a $R
  [ "$got_s" = $WANT_SRCML ] || { fail "libsrcml sha256 differs"; return 1; }
  t0=$(date +%s); sudo -u ec2-user -i bash /home/ec2-user/pf-check-p$K.sh | tee -a $R
  got=$(sha256sum $P/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet 2>/dev/null | cut -d' ' -f1)
  echo "libexpat Parquet sha256 $got ($(( $(date +%s) - t0 )) s)" | tee -a $R
  [ "$got" = $WANT_PQ ] || { fail "libexpat Parquet sha256 differs from $WANT_PQ"; return 1; }
  local ref; ref=$(jar /data/cregit-ec2)
  [ -n "$ref" ] && [ "$(jar $D)" = "$ref" ] || { fail "blobExec jar of $D ($(jar $D)) differs from /data/cregit-ec2 ($ref)"; return 1; }
  echo "blobExec jar sha256 $ref in /data/cregit-ec2 and $D" | tee -a $R
  echo "CHECK OK $(date -u +%FT%TZ) cregit $CREGIT_COMMIT libexpat $WANT_PQ" | tee -a $R
}
echo "== $(date -u +%FT%TZ) R2 gates start"
for K in $(seq 1 $NPARTS); do gate $K > /data/logs/gate-p$K.out 2>&1 & done
wait
rc=0
for K in $(seq 1 $NPARTS); do echo "p$K: $(tail -1 $E/p$K.check)"; tail -1 $E/p$K.check | grep -q '^CHECK OK' || rc=1; done
echo "R2 done $(date -u +%FT%TZ) rc=$rc"
exit $rc
