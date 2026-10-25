#!/usr/bin/env bash
# R2-gate.sh, machine A (root, through scripts/a/ssm-a.sh or scripts/ssm.sh, after R1): the identity
# gate of each long-row tree's own cregit copy, as the R2 of the light-row machine (census-fed-check):
#   - libsrcml.so.1.1.0 sha256 through the copy's devenv shell = dea4467b... (WANT_SRCML of v1);
#   - the libexpat Parquet sha256 of a ctp.py census run with a scratch ctp clone T/ctp-check (ca113e3, the
#     unpatched v1 code, full steps with the firm step) and scratch output T/libexpat-check/out
#     = 14eb5d72... (WANT_PQ, cregit 57551d7);
#   - the blobExec jar sha256 = that of /data/cregit-ec2.
# Result: T/gate.check (on the volume), last line "CHECK OK <time> cregit <commit> ami <ami> ..." or
# "CHECK FAILED: ...". A tree whose gate.check says CHECK OK for the same cregit commit and the same
# AMI is skipped (a relaunch gates only new or changed copies). The gates run in parallel. Exit 0
# only if all 11 are OK. A rerun moves an earlier scratch clone and output aside (no delete).
set -uo pipefail
L=/data/x1k-long
CREGIT_COMMIT=57551d7ad82a784615c1490623d72cb9dc994ba1
WANT_SRCML=dea4467bb1b0a435e4536be13367325564b82e14ff69b478ad31bf144a8455f3
WANT_PQ=14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
tok=$(curl -s -m 2 -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')
AMI=$(curl -s -m 2 -H "X-aws-ec2-metadata-token: $tok" http://169.254.169.254/latest/meta-data/ami-id)
[ -n "$AMI" ] || { echo "ABORT: no AMI id from IMDS"; exit 1; }
[ -f $L/long.tsv ] || { echo "ABORT: run R1 first"; exit 1; }
jar() { find $1 -name '*.jar' -path '*blobExec*' -newer $1/README.md 2>/dev/null | head -1 | xargs -r sha256sum | cut -c1-16; }
gate() {  # gate PROJECT
  local p=$1 T; T=$(readlink -f $L/$1)
  local R=$T/gate.check D=$T/cregit-ec2 U=/home/ec2-user/x1k-long-gate-$1
  fail() { echo "CHECK FAILED: $*" | tee -a $R; return 1; }
  echo "check of $D started $(date -u +%FT%TZ) on $AMI" > $R; chmod 644 $R
  [ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" = $CREGIT_COMMIT ] || { fail "$D is not at $CREGIT_COMMIT"; return 1; }
  printf '# libexpat check on the cregit copy %s (scratch output).\n[paths]\ncregit_dir = %s\noutput_dir = %s\n' $D $D $T/libexpat-check/out > $T/check.cfg
  chmod 644 $T/check.cfg
  cat > $U.srcml.sh <<U
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cd $D
devenv shell -- bash -c 'sha256sum "\$SRCML_PREFIX/lib/libsrcml.so.1.1.0"'
U
  cat > $U.check.sh <<U
set -uo pipefail
C=$T/ctp-check
[ -d \$C ] && mv \$C \$C.old.\$(date +%s)
git clone -q /data/input/ctp.bundle \$C -b feat/e2e-runner
cd \$C; [ "\$(git rev-parse --short HEAD)" = ca113e3 ] || { echo "wrong ctp HEAD"; exit 1; }
ln -s $T/ctp/.venv .venv
export CTP_CONFIG=$T/check.cfg
[ -d $T/libexpat-check/out ] && mv $T/libexpat-check/out $T/libexpat-check/out.old.\$(date +%s)
mkdir -p $T/libexpat-check/out
.venv/bin/python ctp.py census --manifest /data/input/manifest.libexpat.tsv --project-meta /data/input/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10 > $T/logs/check.log 2>&1
echo "census rc=\$?"
U
  chown ec2-user: $U.srcml.sh $U.check.sh
  local got_s got t0 ref
  got_s=$(sudo -u ec2-user -i bash $U.srcml.sh 2>/dev/null | grep -o '^[0-9a-f]\{64\}' | tail -1)
  echo "libsrcml.so.1.1.0 sha256 $got_s (copy $D)" | tee -a $R
  [ "$got_s" = $WANT_SRCML ] || { fail "libsrcml sha256 differs"; return 1; }
  t0=$(date +%s); sudo -u ec2-user -i bash $U.check.sh | tee -a $R
  got=$(sha256sum $T/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet 2>/dev/null | cut -d' ' -f1)
  echo "libexpat Parquet sha256 $got ($(( $(date +%s) - t0 )) s)" | tee -a $R
  [ "$got" = $WANT_PQ ] || { fail "libexpat Parquet sha256 differs from $WANT_PQ"; return 1; }
  ref=$(jar /data/cregit-ec2)
  [ -n "$ref" ] && [ "$(jar $D)" = "$ref" ] || { fail "blobExec jar of $D ($(jar $D)) differs from /data/cregit-ec2 ($ref)"; return 1; }
  echo "blobExec jar sha256 $ref in /data/cregit-ec2 and $D" | tee -a $R
  echo "CHECK OK $(date -u +%FT%TZ) cregit $CREGIT_COMMIT ami $AMI libexpat $WANT_PQ" | tee -a $R
}
echo "== $(date -u +%FT%TZ) R2 (machine A) gates, $AMI"
todo=""
for p in $(cut -f1 $L/long.tsv); do T=$(readlink -f $L/$p)
  if tail -1 $T/gate.check 2>/dev/null | grep -q "^CHECK OK .* cregit $CREGIT_COMMIT ami $AMI " \
     && [ "$(sudo -u ec2-user git -C $T/cregit-ec2 rev-parse HEAD)" = $CREGIT_COMMIT ]; then
    echo "$p: CHECK OK already ($(tail -1 $T/gate.check | cut -d' ' -f3)), skipped"
  else todo="$todo $p"; fi
done
for p in $todo; do gate $p > /data/logs/gate-$p.out 2>&1 & done
wait
rc=0
for p in $(cut -f1 $L/long.tsv); do T=$(readlink -f $L/$p)
  echo "$p: $(tail -1 $T/gate.check)"; tail -1 $T/gate.check | grep -q '^CHECK OK' || rc=1; done
echo "R2 (machine A) done $(date -u +%FT%TZ) gated:${todo:- none} rc=$rc"
exit $rc
