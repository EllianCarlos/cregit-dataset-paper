#!/usr/bin/env bash
# build_stage.sh (this machine): stage the v0 tools (${RUNNER_STUDY_REPO} HEAD, committed) and the link files of one
# database version for the v0 run with the organisation columns (ctp schema 2).
#   L=${RUNNER_PROJECTS_TILDE}/cregit-workspace/companies/links-v4.2 bash build_stage.sh
# U-upload.sh uploads stage/ to s3://.../dataset-v0-org/inputs/.
set -euo pipefail
M=${RUNNER_PROJECTS}/${RUNNER_STUDY_REPO}; DS=$M/2026.2-estudos-pesquisa-sistemas/dataset-selection
L=${L:?set L to the links folder, for example ${RUNNER_PROJECTS_TILDE}/cregit-workspace/companies/links-v4.2}
S=$HOME/s3-work/dataset-v0-org/stage
for f in s8-companies/build_v0.py s8-companies/run_v0.py s7-run/final_merge.py; do
  [ -z "$(git -C $M status --porcelain -- $DS/$f)" ] || { echo "ABORT: $f has uncommitted changes"; exit 1; }
done
grep -q '"mapping_sha256"' $L/links.json || { echo "ABORT: $L/links.json has no mapping_sha256 (old build_links.py)"; exit 1; }
grep -q '@' $L/links.json && { echo "ABORT: '@' in links.json"; exit 1; }
[ -e $S.new ] && { echo "ABORT: $S.new exists (an earlier stage stopped)"; exit 1; }; mkdir -p $S.new
for f in s8-companies/build_v0.py s8-companies/run_v0.py s7-run/final_merge.py; do cp $DS/$f $S.new/; done
for f in domain_links.parquet project_links.parquet links.json; do cp $L/$f $S.new/; done
V=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['organisations_version'])" $L/links.json)
echo "${RUNNER_STUDY_REPO} $(git -C $M rev-parse --short HEAD); links $L ($V, $(date -u -r $L/links.json +%FT%TZ))" > $S.new/SOURCE
(cd $S.new && sha256sum build_v0.py run_v0.py final_merge.py domain_links.parquet project_links.parquet links.json SOURCE > SHA256SUMS)
[ -d $S ] && mv $S $S.old.$(date +%s); mv $S.new $S
cat $S/SOURCE; cat $S/SHA256SUMS
