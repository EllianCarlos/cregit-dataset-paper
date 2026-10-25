#!/usr/bin/env bash
# S0-x3-stage.sh (this machine, local only, no AWS): builds stage/, the tools of the x3 machine, and
# stage/SHA256SUMS. It prints the sha256 of stage/SHA256SUMS: R1-x3-setup.sh and U1-upload-x3.sh pin
# it (WANT_SUMS). Run it again after a change of a tool, then put the new value in both scripts.
#   s8-companies (${RUNNER_STUDY_REPO}): extract_domains_v1.py, build_links.py, build_v0.py (build_links.py
#     imports its rules);
#   this kit: x3_report.py, x3_plainblame.py, x3_run.sh;
#   the company database companies.v4.6.duckdb (W) and ref-links/ = W/links-v4.6 (domain_links,
#     project_links, enterprise_audit, links.json: the v1 gate; no address in them).
# SOURCE (not in SHA256SUMS) records the ${RUNNER_STUDY_REPO} commit and whether s8-companies has changes.
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd)
S8=${RUNNER_PROJECTS}/${RUNNER_STUDY_REPO}/2026.2-estudos-pesquisa-sistemas/dataset-selection/s8-companies
W=${RUNNER_PROJECTS}/cregit-workspace/companies
ST=$H/stage
mkdir -p $ST/ref-links
for f in extract_domains_v1.py build_links.py build_v0.py; do install -m 644 $S8/$f $ST/$f; done
for f in x3_report.py x3_plainblame.py x3_run.sh; do install -m 644 $H/$f $ST/$f; done
install -m 644 $W/companies.v4.6.duckdb $ST/companies.v4.6.duckdb
for f in domain_links.parquet project_links.parquet enterprise_audit.parquet links.json; do install -m 644 $W/links-v4.6/$f $ST/ref-links/$f; done
(cd $ST && find . -type f ! -name SHA256SUMS ! -name SOURCE | sed 's#^\./##' | LC_ALL=C sort | xargs sha256sum > SHA256SUMS)
dirty=$(git -C $S8 status --porcelain -- extract_domains_v1.py build_links.py build_v0.py | wc -l)
echo "${RUNNER_STUDY_REPO} $(git -C $S8 rev-parse --short HEAD), s8-companies tool files with uncommitted changes: $dirty; staged $(date -u +%FT%TZ)" > $ST/SOURCE
grep -q $'\x40' $ST/ref-links/links.json && { echo "ABORT: ref-links/links.json holds the at sign"; exit 1; }
cat $ST/SOURCE
echo "files: $(wc -l < $ST/SHA256SUMS); bytes: $(du -cb $(sed 's/^[0-9a-f]*  /'"${ST//\//\\/}"'\//' $ST/SHA256SUMS) | tail -1 | cut -f1)"
echo "WANT_SUMS=$(sha256sum $ST/SHA256SUMS | cut -d' ' -f1)"
