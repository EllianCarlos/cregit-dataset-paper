#!/usr/bin/env bash
# After the company org listing: rebuild the pool with all org repositories,
# re-check the cut language lists, then run the tree pass and the commit counts
# in parallel (REST and GraphQL use separate quotas). Each step is resumable.
set -e
cd "$(dirname "$0")"
echo "chain3 start $(date -u +%FT%TZ)" >> run.log
python3 build_pool.py >> run.log 2>&1
cd ../s3-measure
python3 recheck_languages.py >> run.log 2>&1
echo "chain3: pool rebuilt, S3 restarts $(date -u +%FT%TZ)" >> ../s2-pool/run.log
nice -n 10 python3 commit_counts.py >> commits.stdout.log 2>&1 &
nice -n 10 python3 measure_trees.py >> stdout.log 2>&1
wait
echo "chain3 end $(date -u +%FT%TZ)" >> ../s2-pool/run.log
