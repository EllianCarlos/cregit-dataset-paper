#!/usr/bin/env bash
# restart_spot.sh [--remaining|--dry-run] a|b : run every unfinished workload of spot half a|b on a
# new one-time spot instance, after a spot interruption (or any loss of the instance). Run it on this
# machine. Since 2026-10-09 ~17:00 UTC a half carries two kinds of census:
#   b3: the rest of batch3<a|b> (share manifest upload/manifest.batch3<a|b>.tsv, done prefix
#       batch3/<a|b>/done/), census-b3@<part>;
#   b5: the batch5 / batch1rest parts of the half (~/s3-work/ec2-batch5/upload/parts.tsv and
#       parts.assign.tsv; done prefix <workload>/<part>/done/), census-b5@<id>.
#   fed (since 2026-10-09 ~20:30 UTC): the fed parts of batch 6 and later, one workload per line of
#       ~/s3-work/ec2-batch6/feed.tsv (parts.<wl>.tsv and parts.<wl>.assign.tsv in its dir; done prefix
#       <workload>/<part>/done/), census-fed@<id>, started one by one by census-fed-feeder.
# The remaining work of each = its share minus every project with done/<project>/OK; the instance
# computes the same itself (census-b3-prep, census-b5-prep, census-fed-enqueue) and starts only
# censuses with work left.
#  --remaining: print the remaining counts ("... total N") and exit 0; nothing is launched.
#  --dry-run:   also check for a live instance and print the relaunch plan; nothing is launched.
#  1. Exits 0 if nothing remains (every workload of the half complete); refuses (exit 1) if an
#     instance tagged Name=cregit-census-batch3<a|b> is still pending/running/stopping.
#  2. Launches one spot instance with launch_fleet.sh: EC2 Fleet (instant, price-capacity-optimized)
#     over the x86 NVMe types (m6id/c6id/r6id/m6idn/r6idn/i4i/m5d/m5dn .24/.32xlarge) in all 4 AZs,
#     from the batch 3 AMI (launch template cregit-census-batch3-spot). TYPES narrows the list.
#     (Fallback without the AMI: FULL=1, launch_spot.sh m6id.24xlarge, b3 only.)
#  3. Waits for SSM, then via scripts/ssm.sh, in this order: the layout (a: one XFS per disk; b: RAID0
#     /data), inputs (sha256), cregit from the AMI and the batch 3 scripts (restore-<x>.sh); the
#     batch 5 scripts (s5-files-1/2.sh, which also install census-spot-decide and the patched
#     census-b3-finalize); if b3 has work left: census-b3-parts-init, its identity check and
#     census-b3-start (gate-<x>.sh); if b5 has work left: census-b5-prep, -parts-init (own loop XFS,
#     ctp clone and cregit copy per part), census-b5-check (identity check on one new copy) and
#     census-b5-start (s5-relaunch-<x>.sh); always the fed scripts (s6-files-0/1/2.sh, which also
#     install the census-spot-decide with the "fed" word); if fed has work left: for each workload of
#     feed.tsv, census-fed-workload (its cregit commit) and census-fed-enqueue (queue the parts with
#     work left; the feeder starts them as slots free) (s6-relaunch-<x>.sh). The instance terminates
#     itself only when every census on it has finalized and the fed queue is empty
#     (census-spot-decide). The local watchdog caps restarts at 3 per half.
# Watch: aws s3 cp s3://${RUNNER_BUCKET}/batch3/<a|b>/live/progress.txt - and
#        aws s3 cp s3://${RUNNER_BUCKET}/batch5/<a|b>1/live/progress.txt -
set -euo pipefail
cd "$(dirname "$0")"
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
mode=run; case ${1:-} in --remaining) mode=remaining; shift ;; --dry-run) mode=dry; shift ;; esac
x=${1:-}; case $x in a|b) ;; *) echo "usage: $0 [--remaining|--dry-run] a|b" >&2; exit 2 ;; esac
B=s3://${RUNNER_BUCKET}; S3=$B/batch3
S5=${S5_UPLOAD:-$HOME/s3-work/ec2-batch5/upload}; S5S=${S5_SCRIPTS:-$HOME/s3-work/ec2-batch5/scripts}
FEED=${FEED_TSV:-$HOME/s3-work/ec2-batch6/feed.tsv}; S6S=${S6_SCRIPTS:-$HOME/s3-work/ec2-batch6/scripts}
oks() { { aws s3 ls "$1" --recursive 2>/dev/null || true; } | awk '$4 ~ /\/OK$/ {n=split($4,a,"/"); print a[n-1]}' | sort -u; }
names() { grep -v -e '^#' -e '^[[:space:]]*$' "$1" | cut -f1 | sort -u; }
b3_left=$(comm -23 <(names upload/manifest.batch3$x.tsv) <(oks "$S3/$x/done/") | grep -c . || true)
b5_left=0; b5_desc=""; b5_ids=""
while IFS=$'\t' read -r h wl p rest; do
  [ "$h" = "$x" ] || continue
  n=$(comm -23 <(awk -F'\t' -v w=$wl -v q=$p '$1==w && $2==q {print $3}' "$S5/parts.assign.tsv" | sort -u) <(oks "$B/$wl/$p/done/") | grep -c . || true)
  b5_left=$((b5_left + n)); b5_desc="$b5_desc $wl$p=$n"; b5_ids="$b5_ids $wl$p"
done < <(grep -v '^#' "$S5/parts.tsv" | tail -n +2)
fed_left=0; fed_desc=""; fed_wls=""
while IFS=$'\t' read -r fwl fdir fcommit fbundle fbsha fpq; do
  case $fwl in ''|'#'*) continue ;; esac
  wn=0
  # one listing per workload (not one per part): the keys <wl>/<part>/done/<project>/OK
  fok=$({ aws s3 ls "$B/$fwl/" --recursive 2>/dev/null || true; } | awk '$4 ~ /\/done\/[^\/]+\/OK$/ {print $4}')
  while IFS=$'\t' read -r h wl p rest; do
    [ "$h" = "$x" ] || continue
    n=$(comm -23 <(awk -F'\t' -v w=$wl -v q=$p '$1==w && $2==q {print $3}' "$fdir/parts.$fwl.assign.tsv" | sort -u) <(grep "^$wl/$p/done/" <<<"$fok" | awk -F/ '{print $(NF-1)}' | sort -u) | grep -c . || true)
    wn=$((wn + n)); fed_desc="$fed_desc $wl$p=$n"
  done < <(grep -v '^#' "$fdir/parts.$fwl.tsv" | tail -n +2)
  fed_left=$((fed_left + wn)); [ "$wn" -gt 0 ] && fed_wls="$fed_wls $fwl"
done < <([ -f "$FEED" ] && cat "$FEED")
total=$((b3_left + b5_left + fed_left))
echo "spot $x remaining: b3 batch3$x=$b3_left; b5$b5_desc; fed$fed_desc; total $total"
[ $mode = remaining ] && exit 0
[ "$total" = 0 ] && { echo "spot $x: every workload complete (no project without done/OK); nothing to relaunch"; exit 0; }
live=$(aws ec2 describe-instances --filters Name=tag:Name,Values=cregit-census-batch3$x Name=instance-state-name,Values=pending,running,stopping \
       --query 'Reservations[].Instances[].InstanceId' --output text)
[ -z "$live" ] || { echo "spot $x still has an instance: $live (stop or wait for it first)"; exit 1; }
layout=layout-raid.sh; [ "$x" = a ] && layout=layout-fsN.sh
plan="restore-$x.sh (X=$x + $layout restore-inputs.sh spot-files.sh) -> s5-files-1.sh s5-files-2.sh"
[ "$b3_left" -gt 0 ] && plan="$plan -> gate-$x.sh (censuses += b3; gate-start.sh)"
[ "$b5_left" -gt 0 ] && plan="$plan -> s5-relaunch-$x.sh (census-b5-prep/-parts-init/-check/-start:$b5_ids)"
plan="$plan -> s6-files-0/1/2.sh"
[ "$fed_left" -gt 0 ] && plan="$plan -> s6-relaunch-$x.sh (census-fed-workload + census-fed-enqueue:$fed_wls)"
echo "plan: launch_fleet.sh $x ${TYPES:-}; $plan"
[ $mode = dry ] && { echo "dry run: nothing launched"; exit 0; }
fromami=1; [ "${FULL:-0}" = 1 ] && fromami=0
if [ $fromami = 1 ]; then
  out=$(./launch_fleet.sh "$x" ${TYPES:-}) || { echo "no spot capacity for any type/AZ now; try again later"; exit 1; }
  read -r id itype sub <<<"$out"
  az=$(aws ec2 describe-subnets --subnet-ids "$sub" --query 'Subnets[0].AvailabilityZone' --output text); ami=$(cat ami.txt)
else
  itype=m6id.24xlarge; ami=${RUNNER_AMI_BASE}; id=""
  for az in ${RUNNER_AWS_REGION}b ${RUNNER_AWS_REGION}a ${RUNNER_AWS_REGION}c ${RUNNER_AWS_REGION}d; do id=$(./launch_spot.sh "$x" "$az") && break || id=""; done
  [ -n "$id" ] || { echo "no m6id.24xlarge spot capacity now"; exit 1; }
fi
price=$(aws ec2 describe-spot-price-history --instance-types "$itype" --availability-zone "$az" --product-descriptions Linux/UNIX --max-items 1 --query 'SpotPriceHistory[0].SpotPrice' --output text | head -1)
echo "launched $id: $itype in $az (spot price now \$$price/h), AMI $ami"
echo "$x=$id type=$itype az=$az ami=$ami price=$price launched=$(date -u +%FT%TZ) workloads: b3=$b3_left b5=$b5_left fed=$fed_left" >> instances.txt
aws ec2 wait instance-running --instance-ids "$id"
for i in $(seq 1 60); do
  [ "$(aws ssm describe-instance-information --filters Key=InstanceIds,Values=$id --query 'InstanceInformationList[0].PingStatus' --output text)" = Online ] && break; sleep 10
done
cd scripts
./gen-spot-install.sh >/dev/null
(cd "$S5S" && ./gen-s5-files.sh >/dev/null)
if [ $fromami = 1 ]; then
  { echo "X=$x"; cat $layout restore-inputs.sh spot-files.sh; } > restore-$x.sh
  I=$id TAILN=20 ./ssm.sh restore-$x.sh 5400
else
  I=$id TAILN=20 ./ssm.sh setup-$x.sh 5400
  [ "$x" = a ] && I=$id TAILN=20 ./ssm.sh relayout-a.sh 3600
  { echo "X=$x"; cat spot-files.sh; } > restore-$x.sh
  I=$id TAILN=20 ./ssm.sh restore-$x.sh 3600
fi
I=$id TAILN=5 ./ssm.sh "$S5S/s5-files-1.sh" 600
I=$id TAILN=5 ./ssm.sh "$S5S/s5-files-2.sh" 600
if [ "$b3_left" -gt 0 ]; then
  { echo "X=$x"; echo 'mkdir -p /etc/cregit-census; touch /etc/cregit-census/censuses; grep -qx b3 /etc/cregit-census/censuses || echo b3 >> /etc/cregit-census/censuses'; cat gate-start.sh; } > gate-$x.sh
  I=$id TAILN=40 ./ssm.sh gate-$x.sh 3600
fi
if [ "$b5_left" -gt 0 ] && [ $fromami = 1 ]; then
  { echo "X=$x"; cat "$S5S/s5-relaunch.sh"; } > "$S5S/s5-relaunch-$x.sh"
  I=$id TAILN=40 ./ssm.sh "$S5S/s5-relaunch-$x.sh" 3600
fi
(cd "$S6S" && ./gen-s6-files.sh >/dev/null)
for n in 0 1 2; do I=$id TAILN=5 ./ssm.sh "$S6S/s6-files-$n.sh" 600; done
if [ "$fed_left" -gt 0 ] && [ $fromami = 1 ]; then
  { echo "X=$x"; echo 'set -uo pipefail'
    while IFS=$'\t' read -r fwl fdir fcommit fbundle fbsha fpq; do
      case " $fed_wls " in *" $fwl "*) ;; *) continue ;; esac
      case $fcommit in
        pending) echo "[ -f /etc/cregit-census/fed/wl/$fwl.env ] || /usr/local/bin/census-fed-workload $fwl --pending" ;;
        base) echo "/usr/local/bin/census-fed-workload $fwl --base" ;;
        *) echo "/usr/local/bin/census-fed-workload $fwl --commit $fcommit --bundle $fbundle --bundle-sha256 $fbsha --want-pq $fpq" ;;
      esac
      echo "/usr/local/bin/census-fed-enqueue $fwl \$X || exit 1"
    done < <(grep -v '^#' "$FEED")
    echo 'sleep 70; echo "feeder: $(cat /run/census-fed-feeder.status)"'
  } > "$S6S/s6-relaunch-$x.sh"
  I=$id TAILN=40 ./ssm.sh "$S6S/s6-relaunch-$x.sh" 3600
fi
echo "spot $x restarted on $id ($az). Watch: aws s3 cp $S3/$x/live/progress.txt - ; aws s3 cp $B/batch5/${x}1/live/progress.txt - ; aws s3 cp $B/feed/$x/live/progress.txt -"
# 2026-10-12: the three steps after every relaunch (spot a: slots = 12 and the local-a parts out of
# the fed queue; both: formatBlame.pl 57551d7 in the b3/b5 part copies). A failure here does not
# fail the relaunch: post_relaunch.sh prints it, and you run it again by hand.
../post_relaunch.sh "$x" "$id" || echo "post_relaunch.sh $x $id: rc=$? (the relaunch itself is OK; run ~/s3-work/ec2-batch3/post_relaunch.sh $x $id again)"
