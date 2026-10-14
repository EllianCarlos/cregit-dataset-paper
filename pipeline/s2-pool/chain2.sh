#!/usr/bin/env bash
# S2 again with the new inputs (no candidates.csv), then S3. Each step is resumable.
set -e
cd "$(dirname "$0")"
echo "chain2 start $(date -u +%FT%TZ)" >> run.log
nice -n 10 python3 resolve.py >> stdout.log 2>&1
nice -n 10 python3 resolve_rest.py >> stdout.log 2>&1
python3 build_pool.py >> run.log 2>&1
cd ../s3-measure
python3 recheck_languages.py >> run.log 2>&1
echo "chain2: S2 done, S3 starts $(date -u +%FT%TZ)" >> ../s2-pool/run.log
nice -n 10 python3 measure_trees.py >> stdout.log 2>&1
echo "chain2 end $(date -u +%FT%TZ)" >> ../s2-pool/run.log
