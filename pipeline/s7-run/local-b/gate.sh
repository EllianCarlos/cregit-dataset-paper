#!/usr/bin/env bash
# gate.sh: the libexpat identity gate of census-local-b, as gate-blamelimit/gate.sh:
# a fresh scratch ctp clone at ca113e3, the cregit copy census-local-b/cregit (57551d7), the flags of census-fed-check.
set -uo pipefail
L=/home/ellianco/Projects/cregit-workspace/census-local-b
G=$L/gate
C=$G/ctp-check
[ -d $C ] && mv $C $C.old.$(date +%s)
git clone -q ~/Projects/cregit-token-pipeline $C -b feat/e2e-runner
cd $C; [ "$(git rev-parse --short HEAD)" = ca113e3 ] || { echo "wrong ctp HEAD"; exit 1; }
python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0
printf '# libexpat gate, cregit copy %s, scratch output.\n[paths]\ncregit_dir = %s\noutput_dir = %s\n' $L/cregit $L/cregit $G/out > $G/check.cfg
export CTP_CONFIG=$G/check.cfg
[ -d $G/out ] && mv $G/out $G/out.old.$(date +%s)
mkdir -p $G/out
echo "=== $(date -u +%FT%TZ) gate start (cregit $(git -C $L/cregit rev-parse --short HEAD), ctp $(git rev-parse --short HEAD))"
.venv/bin/python ctp.py census --manifest $G/manifest.libexpat.tsv --project-meta $G/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10
echo "census rc=$?"
P=$G/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet
echo "libexpat Parquet: $(sha256sum $P 2>/dev/null | cut -d' ' -f1) $(stat -c %s $P 2>/dev/null) bytes"
echo "PLAIN-BLAME lines in the pipeline logs: $(cat $C/state/libexpat__libexpat/logs/pipeline-*.log 2>/dev/null | grep -c '^PLAIN-BLAME')"
grep -h "Newly processed" $C/state/libexpat__libexpat/logs/pipeline-*.log 2>/dev/null
echo "=== $(date -u +%FT%TZ) gate end"
