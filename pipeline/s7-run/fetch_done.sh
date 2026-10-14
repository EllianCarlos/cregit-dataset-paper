#!/usr/bin/env bash
# fetch_done.sh: copy the finished project files of the EC2 runs from S3 to this machine, then check
# each Parquet against the sha256 in its OK file. Download only: it never writes to S3.
#   ./fetch_done.sh            all runs in RUNS
#   RUNS="batch2" ./fetch_done.sh
# Output: $CENSUS_CLOUD_DIR/<run>/.../<project>/ (the S3 layout), plus
#   verified.tsv   one line per checked project: time, path, sha256
#   failed.tsv     one line per project whose Parquet does not match its OK sha256
#   fetch.log      one line per run and pass
# A project is checked again only when its OK file changes. Runs every 30 min from the transient
# user timer census-fetch (see README.md), so new finished projects arrive by themselves.
set -uo pipefail
export AWS_PROFILE=ellianco-personal AWS_REGION=us-west-2 AWS_PAGER=""  # the shell can carry another profile
B=s3://cregit-census-905418043997-usw2
D=${CENSUS_CLOUD_DIR:-$HOME/Projects/cregit-workspace/census-cloud}
RUNS=${RUNS:-"batch1rest batch2 batch3 batch3L batch4 batch5 batch5L batch6 batch6L $(seq -f "batch%g" -s " " 7 26) L7-20 L22 L7-20b L23 L1r"}
mkdir -p "$D"
exec 9>"$D/.lock"
flock -n 9 || { echo "$(date -u +%FT%TZ) another pass runs; skip" >>"$D/fetch.log"; exit 0; }

for r in $RUNS; do
  t0=$(date +%s)
  if aws s3 sync "$B/$r/" "$D/$r/" --exclude '*' --include '*done/*' --include '*final/*' \
       --only-show-errors 2>>"$D/fetch.log"; then st=ok; else st="sync exit $?"; fi
  echo "$(date -u +%FT%TZ) $r: $st ($(( $(date +%s) - t0 )) s)" >>"$D/fetch.log"
done

# Check each project whose OK file is newer than its .checked marker.
find "$D" -path '*/done/*' -name OK -type f | while read -r ok; do
  dir=$(dirname "$ok")
  [ "$dir/.checked" -nt "$ok" ] && continue
  # Two OK formats: "<sha256>  <name>-dataset.parquet" (batch2, batch3L, batch4) and
  # "parquet_sha256 <sha256>" (the spot parts and the fed parts), for <dir name>-dataset.parquet.
  line=$(grep -E '^[0-9a-f]{64}  ' "$ok" | head -1)
  if [ -z "$line" ]; then
    h=$(sed -n 's/^parquet_sha256 \([0-9a-f]\{64\}\)$/\1/p' "$ok" | head -1)
    [ -n "$h" ] && line="$h  $(basename "$dir")-dataset.parquet"
  fi
  [ -n "$line" ] || { printf '%s\t%s\tno sha256 line in OK\n' "$(date -u +%FT%TZ)" "$dir" >>"$D/failed.tsv"; continue; }
  if (cd "$dir" && sha256sum -c --status <<<"$line"); then
    printf '%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "${dir#"$D"/}" "${line%% *}" >>"$D/verified.tsv"
    touch "$dir/.checked"
  else
    printf '%s\t%s\tsha256 mismatch or file missing\n' "$(date -u +%FT%TZ)" "${dir#"$D"/}" >>"$D/failed.tsv"
  fi
done
echo "$(date -u +%FT%TZ) pass done: $(find "$D" -path '*/done/*' -name .checked | wc -l) projects verified" >>"$D/fetch.log"
