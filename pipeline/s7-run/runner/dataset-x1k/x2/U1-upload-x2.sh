#!/usr/bin/env bash
# U1-upload-x2.sh (run by the user: `! bash ~/s3-work/dataset-x1k/x2/U1-upload-x2.sh`): uploads the X1
# result, the x1k final sidecar and its sha256, to s3://BUCKET/dataset-x1k/raw-tools/, for X2.
# It checks the sha256 before and the sizes after. It writes nothing else. The tools final_merge.py and
# rewrite_meta_columns.py of v1 are already in s3://BUCKET/dataset-v1/tools/ (R1-x2 checks them).
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
S=${RUNNER_PROJECTS_TILDE}/${RUNNER_STUDY_REPO}/2026.2-estudos-pesquisa-sistemas/dataset-selection/x1k
D=s3://${RUNNER_BUCKET}/dataset-x1k/raw-tools
WANT=1520c5f4d8909b3625c73bdea3cc08f23fced0a77f3722ec0809acd80de96f35
(cd $S && sha256sum -c project_meta.x1k.final.json.sha256)
[ "$(cut -d' ' -f1 $S/project_meta.x1k.final.json.sha256)" = $WANT ] || { echo "ABORT: the sidecar is not $WANT (X1 changed: update WANT here and in R1-x2-setup.sh)"; exit 1; }
for f in project_meta.x1k.final.json project_meta.x1k.final.json.sha256; do
  aws s3 cp $S/$f $D/$f --only-show-errors
  [ "$(aws s3 ls $D/$f | awk '{print $3}')" = "$(stat -c %s $S/$f)" ] || { echo "ABORT: size check of $f"; exit 1; }
  echo "uploaded $f ($(stat -c %s $S/$f) B)"
done
echo "U1-x2 done"
