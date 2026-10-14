#!/usr/bin/env bash
# set-cregit.sh COMMIT BUNDLE_SHA256 WANT_PQ [WANT_SRCML] [--go] (local): give batch 6 its cregit commit,
# after the user uploaded the bundle (stage-cregit.sh). Without --go it only checks the bundle in S3 and
# prints the plan. With --go:
#   1. feed.tsv: the batch6 line gets COMMIT, the bundle URL, its sha256 and WANT_PQ (relaunches use them);
#   2. each spot instance: census-fed-workload batch6 --commit ... (the feeder then starts the queued
#      parts as slots free: part-init checks each new copy out at COMMIT, census-fed-check gates it
#      against WANT_PQ), then one feeder pass;
#   3. the big EC2: census-batch6L-cregit --commit ... (checkout of /b6L/cregit-ec2 and its gate; the
#      waiter starts census-batch6L once the gate passed and slots, memory and disk allow).
# --base instead of COMMIT...: run batch 6 on 95cdc88 (the AMI commit, batch 5 gate values; no bundle).
set -euo pipefail
cd "$(dirname "$0")"
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
B=s3://${RUNNER_BUCKET}
# the current spot ids: the last a= and b= lines of instances.txt (restart_spot.sh appends one per launch)
IT=$HOME/s3-work/ec2-batch3/instances.txt
SPOTS="$(grep '^a=' $IT | tail -1 | sed 's/^a=\([^ ]*\).*/\1/') $(grep '^b=' $IT | tail -1 | sed 's/^b=\([^ ]*\).*/\1/')"; BIG=${RUNNER_EC2_BIG}
go=0; for a in "$@"; do [ "$a" = --go ] && go=1; done
if [ "${1:-}" = --base ]; then
  fedargs="--base"; largs="--base"; line=$(printf 'batch6\t%s\tbase\t-\t-\t-' "$PWD/upload")
else
  C=${1:?commit}; BS=${2:?bundle sha256}; PQ=${3:?libexpat sha256}; SR=${4:-}; [ "$SR" = --go ] && SR=""
  short=${C:0:7}; url=$B/cregit/cregit-$short.bundle
  [[ $C =~ ^[0-9a-f]{40}$ ]] || { echo "COMMIT must be the full 40-hex SHA" >&2; exit 2; }
  aws s3 ls "$url" || { echo "bundle $url is not in S3 yet (the user uploads it)" >&2; exit 1; }
  grep -q "^$BS " upload-cregit/SHA256SUMS.$short || { echo "BUNDLE_SHA256 is not the staged one (upload-cregit/SHA256SUMS.$short)" >&2; exit 1; }
  extra=""; [ -n "$SR" ] && extra="--want-srcml $SR"
  fedargs="--commit $C --bundle $url --bundle-sha256 $BS --want-pq $PQ $extra"; largs="$fedargs"
  line=$(printf 'batch6\t%s\t%s\t%s\t%s\t%s' "$PWD/upload" "$C" "$url" "$BS" "$PQ")
fi
echo "plan: feed.tsv batch6 -> [$line]; spots: census-fed-workload batch6 $fedargs; big EC2: census-batch6L-cregit $largs"
[ $go = 1 ] || { echo "(no --go: nothing changed)"; exit 0; }
cp -p feed.tsv feed.tsv.bak.$(date +%s); awk -v l="$line" -F'\t' 'BEGIN{OFS="\t"} $1=="batch6"{print l; next} {print}' feed.tsv > feed.tsv.new && mv feed.tsv.new feed.tsv
printf 'set -uo pipefail\n/usr/local/bin/census-fed-workload batch6 %s || exit 1\n/usr/local/bin/census-fed-feeder; echo "feeder rc=$?"; tail -n 5 /data/logs/fed-feeder.log 2>/dev/null | cut -c1-220\n' "$fedargs" > scripts/s6-setcommit.sh
for I in $SPOTS; do I=$I TAILN=20 scripts/ssm.sh scripts/s6-setcommit.sh 3600 | tee out/s6-setcommit-$I.out; done
printf 'set -uo pipefail\n/usr/local/bin/census-batch6L-cregit %s; echo "gate rc=$?"; /usr/local/bin/census-batch6L-wait --decide-only | cut -c1-400\n' "$largs" > scripts/L3-setcommit.sh
I=$BIG TAILN=20 scripts/ssm.sh scripts/L3-setcommit.sh 3600 | tee out/L3-setcommit.out
