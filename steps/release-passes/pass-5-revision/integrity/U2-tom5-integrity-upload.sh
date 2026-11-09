#!/usr/bin/env bash
# U2-tom5-integrity-upload.sh (run by the user: `! bash ~/s3-work/dataset-tom-5/U2-tom5-integrity-upload.sh`): uploads
# integrity_check.py to s3://BUCKET/dataset-release/dataset-v1.0.0-tom-5/integrity/tools/ for I1-tom5-integrity.sh.
# It checks the sha256 before (WANT_CHECK, the same value as in I1) and the size after. It writes nothing else.
set -euo pipefail
export AWS_PROFILE=AWS_PROFILE_NAME AWS_REGION=us-west-2 AWS_PAGER=""
H=$(cd "$(dirname "$0")" && pwd)
D=s3://BUCKET_NAME/dataset-release/dataset-v1.0.0-tom-5/integrity/tools
WANT_CHECK=1c9ea571592fa84c73318035223c4ecbbee0de9fae24ae6115980ce5b538e30e
F=$H/integrity_check.py
[ "$(sha256sum $F | cut -d' ' -f1)" = $WANT_CHECK ] || { echo "ABORT: integrity_check.py is not ${WANT_CHECK:0:12}"; exit 1; }
grep -q "^WANT_CHECK=$WANT_CHECK$" $H/I1-tom5-integrity.sh || { echo "ABORT: I1 has another WANT_CHECK"; exit 1; }
aws s3 cp $F $D/integrity_check.py --only-show-errors
n=$(aws s3api head-object --bucket BUCKET_NAME \
      --key dataset-release/dataset-v1.0.0-tom-5/integrity/tools/integrity_check.py --query ContentLength --output text)
[ "$n" = "$(stat -c %s $F)" ] || { echo "ABORT: the S3 size is $n"; exit 1; }
echo "uploaded integrity_check.py ($n B, ${WANT_CHECK:0:12}) to $D/"
echo "U2-tom5 done"
