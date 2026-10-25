#!/usr/bin/env bash
# R2-gate.sh (the x1k instance, root, through ssm.sh, after R1): the identity gate of every part's
# own cregit copy, the census-fed-check of the v1 spot parts, run for the 4 parts at once:
#   - libsrcml.so.1.1.0 sha256 through the copy's own devenv shell = dea4467b... (WANT_SRCML of v1);
#   - the libexpat Parquet sha256 of a census with a scratch ctp clone /dataK/x1k/ctp-check (ca113e3,
#     the unpatched v1 code, full steps with the firm step) and scratch output
#     /dataK/x1k/libexpat-check/out, flags of the v1 check = 14eb5d72... (WANT_PQ of batches 7-26,
#     cregit 57551d7);
#   - the blobExec jar sha256 = that of /data/cregit-ec2.
# Result: /etc/dataset-x1k/pK.check, last line "CHECK OK ..." or "CHECK FAILED: ..."; exit 0 only if
# all 4 are OK. A rerun moves an earlier scratch clone and output aside (no delete).
set -uo pipefail
E=/etc/dataset-x1k
CREGIT_COMMIT=57551d7ad82a784615c1490623d72cb9dc994ba1
WANT_SRCML=dea4467bb1b0a435e4536be13367325564b82e14ff69b478ad31bf144a8455f3
WANT_PQ=14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
jar() { find $1 -name '*.jar' -path '*blobExec*' -newer $1/README.md 2>/dev/null | head -1 | xargs -r sha256sum | cut -c1-16; }
gate() {
  local K=$1 P=/data$1/x1k R=$E/p$1.check D=/data$1/x1k/cregit-ec2
  fail() { echo "CHECK FAILED: $*" | tee -a $R; return 1; }
  echo "check of $D started $(date -u +%FT%TZ)" > $R; chmod 644 $R
  [ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" = $CREGIT_COMMIT ] || { fail "$D is not at $CREGIT_COMMIT"; return 1; }
  printf '# libexpat check on the cregit copy %s (scratch output).\n[paths]\ncregit_dir = %s\noutput_dir = %s\n' $D $D $P/libexpat-check/out > $E/p$K.check.cfg
  chmod 644 $E/p$K.check.cfg
  cat > /home/ec2-user/x1k-srcml-p$K.sh <<U
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cd $D
devenv shell -- bash -c 'sha256sum "\$SRCML_PREFIX/lib/libsrcml.so.1.1.0"'
U
  cat > /home/ec2-user/x1k-check-p$K.sh <<U
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
  chown ec2-user: /home/ec2-user/x1k-srcml-p$K.sh /home/ec2-user/x1k-check-p$K.sh
  local got_s got t0
  got_s=$(sudo -u ec2-user -i bash /home/ec2-user/x1k-srcml-p$K.sh 2>/dev/null | grep -o '^[0-9a-f]\{64\}' | tail -1)
  echo "libsrcml.so.1.1.0 sha256 $got_s (copy $D)" | tee -a $R
  [ "$got_s" = $WANT_SRCML ] || { fail "libsrcml sha256 differs"; return 1; }
  t0=$(date +%s); sudo -u ec2-user -i bash /home/ec2-user/x1k-check-p$K.sh | tee -a $R
  got=$(sha256sum $P/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet 2>/dev/null | cut -d' ' -f1)
  echo "libexpat Parquet sha256 $got ($(( $(date +%s) - t0 )) s)" | tee -a $R
  [ "$got" = $WANT_PQ ] || { fail "libexpat Parquet sha256 differs from $WANT_PQ"; return 1; }
  local ref; ref=$(jar /data/cregit-ec2)
  [ -n "$ref" ] && [ "$(jar $D)" = "$ref" ] || { fail "blobExec jar of $D ($(jar $D)) differs from /data/cregit-ec2 ($ref)"; return 1; }
  echo "blobExec jar sha256 $ref in /data/cregit-ec2 and $D" | tee -a $R
  echo "CHECK OK $(date -u +%FT%TZ) cregit $CREGIT_COMMIT libexpat $WANT_PQ" | tee -a $R
}
echo "== $(date -u +%FT%TZ) R2 gates start"
for K in 1 2 3 4; do gate $K > /data/logs/gate-p$K.out 2>&1 & done
wait
rc=0
for K in 1 2 3 4; do echo "p$K: $(tail -1 $E/p$K.check)"; tail -1 $E/p$K.check | grep -q '^CHECK OK' || rc=1; done
echo "R2 done $(date -u +%FT%TZ) rc=$rc"
exit $rc
