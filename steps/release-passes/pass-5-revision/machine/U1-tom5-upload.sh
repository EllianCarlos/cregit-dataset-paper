#!/usr/bin/env bash
# U1-tom5-upload.sh (run by the user: `! bash KIT-FOLDER/U1-tom5-upload.sh`): uploads stage/
# (S1-tom5-stage.sh) to s3://BUCKET/dataset-release/dataset-v1.0.0-tom-5/tools/ for the TOM-5 machine. It checks the
# sha256 of SHA256SUMS (WANT_SUMS, written by S1) and of each file before, and the sizes after. It writes nothing
# else. FORCE=1 uploads a new stage over an earlier one (only before B1 started).
set -euo pipefail
export AWS_PROFILE=AWS_PROFILE_NAME AWS_REGION=us-west-2 AWS_PAGER=""
ST=${TOM_STAGE_DIR:-$(cd "$(dirname "$0")" && pwd)/stage}
D=${TOM_TOOLS_DEST:-s3://BUCKET_NAME/dataset-release/dataset-v1.0.0-tom-5/tools}
WANT_SUMS=da9125463a33d480755cdcb9ec91f6a6fab8292d4e73667785c1d3ed12fb43f6
[ "$WANT_SUMS" != none ] || { echo "ABORT: no stage yet (run S1-tom5-stage.sh)"; exit 1; }
[ "$(sha256sum $ST/SHA256SUMS | cut -d' ' -f1)" = $WANT_SUMS ] || { echo "ABORT: stage/SHA256SUMS is not ${WANT_SUMS:0:12} (run S1 again)"; exit 1; }
(cd $ST && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: a stage file does not match SHA256SUMS"; exit 1; }
n0=$({ aws s3 ls --recursive $D/ || true; } | wc -l)
[ "$n0" = 0 ] || [ "${FORCE:-0}" = 1 ] || { echo "ABORT: $D/ is not empty ($n0 objects); FORCE=1 uploads the new stage over it"; exit 1; }
aws s3 cp --recursive $ST/ $D/ --only-show-errors
L=$(mktemp); aws s3 ls --recursive $D/ | awk '{print $3, $4}' | LC_ALL=C sort > $L
base=${D#s3://*/}
miss=$(cd $ST && { awk '{print $2}' SHA256SUMS; echo SHA256SUMS; echo SOURCE; } | while read -r f; do echo "$(stat -c %s "$f") $base/$f"; done | LC_ALL=C sort | comm -23 - $L | wc -l)
rm -f $L
[ "$miss" = 0 ] || { echo "ABORT: size check: $miss files"; exit 1; }
echo "uploaded $(($(wc -l < $ST/SHA256SUMS) + 2)) files ($(du -sb $ST | cut -f1) B) to $D/"
echo "U1-tom5 done"
