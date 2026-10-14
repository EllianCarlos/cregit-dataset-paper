#!/usr/bin/env bash
# The user runs this (Claude's S3 uploads are denied): ! bash ~/s3-work/upload-L1r.sh
# Uploads the 3 input files of census L1r (batch 1 rerun, L: torvalds__linux and SAP__project-foxhound,
# 2026-10-12) to B/L1r/input/, then reads every object back and checks the sha256 of each. The cregit
# bundle 57551d7 is already in B/cregit/ (upload-cregit-blamelimit.sh, 2026-10-11); this script reads
# it back and checks it too. It prints ALL OK at the end when every check passed.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}
U=$HOME/s3-work/ec2-L1r/upload
C=$HOME/s3-work/upload-cregit-blamelimit
WANT_M=3443e70ac9d78ff3c428bfddc3fa311873f38b161b761637d41b69560f1e6768  # manifest.L1r.tsv
WANT_J=c4c5b946d8f8623d045ea6f0ac872b37ff9e2a5eb0fe12d0ece501329d52c081  # project_meta.L1r.json
WANT_BUNDLE=18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e  # cregit-57551d7.bundle
chk() {  # DIR: the 3 files, SHA256SUMS ok, and the expected manifest and sidecar sha256
  (cd "$1" && [ "$(command ls | wc -l)" -eq 3 ] && sha256sum --quiet -c SHA256SUMS \
    && [ "$(sha256sum manifest.L1r.tsv | cut -d' ' -f1)" = $WANT_M ] \
    && [ "$(sha256sum project_meta.L1r.json | cut -d' ' -f1)" = $WANT_J ])
}
chk $U || { echo "FAIL local files"; exit 1; }
echo "local files ok"
aws s3 cp $U/ $B/L1r/input/ --recursive --only-show-errors || { echo "FAIL upload"; exit 1; }
bad=0
echo "listing of $B/L1r/input/:"
aws s3 ls $B/L1r/input/ | sed 's/^/  /'
d=$(mktemp -d); aws s3 cp $B/L1r/input/ $d/ --recursive --only-show-errors
if chk $d; then echo "L1r: 3 objects, read-back ok (manifest ${WANT_M:0:16}, sidecar ${WANT_J:0:16})"; else echo "L1r: CHECK FAILED"; bad=1; fi
rm -rf "$d"
d=$(mktemp -d); aws s3 cp $B/cregit/cregit-57551d7.bundle $d/ --only-show-errors; aws s3 cp $B/cregit/SHA256SUMS.57551d7 $d/ --only-show-errors
if (cd $d && cmp -s SHA256SUMS.57551d7 $C/SHA256SUMS.57551d7 && sha256sum --quiet -c SHA256SUMS.57551d7 \
    && [ "$(sha256sum cregit-57551d7.bundle | cut -d' ' -f1)" = $WANT_BUNDLE ]); then echo "bundle 57551d7: read-back ok"
else echo "bundle 57551d7: CHECK FAILED"; bad=1; fi
rm -rf "$d"
[ $bad = 0 ] && echo "ALL OK" || { echo "SOME CHECKS FAILED"; exit 1; }
