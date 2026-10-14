#!/usr/bin/env bash
# Wait for the first resolve.py run to end, then run the new slugs and the REST pass.
cd "$(dirname "$0")"
while ! grep -q ' end$' run.log; do sleep 30; done
nice -n 10 python3 resolve.py >> stdout.log 2>&1
nice -n 10 python3 resolve_rest.py >> stdout.log 2>&1
echo "chain end $(date -u +%FT%TZ)" >> run.log
