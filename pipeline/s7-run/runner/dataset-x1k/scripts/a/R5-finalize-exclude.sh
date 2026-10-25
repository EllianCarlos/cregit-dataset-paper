#!/usr/bin/env bash
# R5-finalize-exclude.sh, machine A (root, through scripts/a/ssm-a.sh; written 2026-10-20; idempotent;
# starts and stops nothing). Problem: x1k-long-finalize needs an upload for every row of run.list, but
# notnotype__neuro-book and pur1fying__blue_archive_auto_script fail every time in step 10 ("no .blame
# files found", "no tokens processed": 0 C/C++/Java/Rust files at the pinned commit). Thus the machine
# would write live-a/ALERT and never power off. This script:
#   1. checks that the installed x1k-long-finalize is the R3 text (sha256 4fbb5051...) or already the new one;
#   2. checks the 2 rows: unit not active, not uploaded, newest pipeline log has "no .blame files found";
#   3. writes /data/x1k-long/excluded.tsv ("<p><TAB><reason>", on volume 1) and copies it to live-a/;
#   4. installs the new x1k-long-finalize (the text of R3-install.sh, sha256 076abd7e...): a row in
#      excluded.tsv needs no upload, only "census finished"; DONE says "excluded (<reason>)" for it,
#      and final-a/excluded.tsv is written with the size check.
# Test: scripts/a/test/finalize-exclude-test.sh (FINALIZE TEST OK; the old text gives ALERT).
set -euo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_B1}|${RUNNER_EC2_X1K_B2}) echo "ABORT: $IID is not machine A"; exit 1 ;; esac
B=s3://${RUNNER_BUCKET}; L=/data/x1k-long; F=/usr/local/bin/x1k-long-finalize
OLD=4fbb50511a01f85d16c4d452235522090ab2c87ee49ce3d74d992f161b3ce9bd
NEW=076abd7e0f21987319077bb619d28d4282c376ae4464eb845f85c10e1e250460
have=$(sha256sum $F | cut -d' ' -f1)
[ "$have" = $OLD ] || [ "$have" = $NEW ] || { echo "ABORT: $F has sha256 $have, not the R3 text and not the new text"; exit 1; }
R='no tokens: 0 C/C++/Java/Rust files at the pinned commit (step 10 of each attempt: no .blame files found, no tokens processed)'
for p in notnotype__neuro-book pur1fying__blue_archive_auto_script; do T=$(readlink -f $L/$p)
  ! systemctl is-active -q x1k-long@$p || { echo "ABORT: x1k-long@$p is active"; exit 1; }
  [ ! -e $T/uploaded/$p ] || { echo "ABORT: $p is uploaded"; exit 1; }
  lg=$(ls -t $T/ctp/state/$p/logs/pipeline-2*.log | head -1)
  grep -q 'no .blame files found' "$lg" || { echo "ABORT: $lg has no 'no .blame files found'"; exit 1; }
  echo "$p: unit $(systemctl is-active x1k-long@$p), not uploaded, $(ls $T/ctp/state/$p/logs/pipeline-2*.log | wc -l) pipeline logs, newest $(basename $lg): no .blame files found"
done
printf 'notnotype__neuro-book\t%s\npur1fying__blue_archive_auto_script\t%s\n' "$R" "$R" > $L/excluded.tsv.new
if [ -f $L/excluded.tsv ] && ! cmp -s $L/excluded.tsv $L/excluded.tsv.new; then echo "ABORT: $L/excluded.tsv exists with other content"; rm -f $L/excluded.tsv.new; exit 1; fi
mv -f $L/excluded.tsv.new $L/excluded.tsv; chown ec2-user: $L/excluded.tsv
aws s3 cp $L/excluded.tsv $B/dataset-x1k/live-a/excluded.tsv --only-show-errors
[ "$(aws s3 ls $B/dataset-x1k/live-a/excluded.tsv | awk '{print $3}')" = "$(stat -c %s $L/excluded.tsv)" ] || { echo "ABORT: live-a/excluded.tsv size check failed"; exit 1; }
echo "excluded.tsv: $(wc -l < $L/excluded.tsv) rows, $(stat -c %s $L/excluded.tsv) B, also in live-a/excluded.tsv (size checked)"
cat > $F.new <<'EOF_x1k_long_finalize'
#!/usr/bin/env bash
# x1k-long-finalize (root; after each unit ends and every 15 min): see R3-install.sh of machine A.
set -uo pipefail
B=s3://${RUNNER_BUCKET}
E=/etc/dataset-x1k; L=/data/x1k-long
# excluded.tsv (on volume 1; "<p><TAB><reason>"): rows that end without an upload by decision
# (2026-10-20: no tokens). Such a row counts as finished when its unit wrote "census finished".
X=$L/excluded.tsv
excluded() { [ -f $X ] && cut -f1 $X | grep -q -x -F "$1"; }
[ -f $L/started ] && [ -f $L/run.list ] || exit 0
[ -e /run/x1k-spot-interrupted ] && exit 0
for p in $(cat $L/run.list); do systemctl is-active -q x1k-long@$p && exit 0; done
[ -f $E/final-a-DONE ] && exit 0
echo "$(date -u +%FT%TZ) all units inactive: final upload"
sudo -u ec2-user /usr/local/bin/x1k-long-upload
clean=1; T=$(mktemp -d)
for p in $(cat $L/run.list); do R=$(readlink -f $L/$p); C=$R/ctp; mkdir -p $T/$p
  grep -q 'census finished rc=' $R/logs/run.log 2>/dev/null || clean=0
  [ -e $R/uploaded/$p ] || excluded $p || clean=0
  for f in ledger.jsonl runs.log metrics.tsv resources.tsv; do [ -f $C/$f ] && cp $C/$f $T/$p/; done
  cp $R/logs/run.log $R/manifest.tsv $R/run.env $T/$p/ 2>/dev/null
  [ -f $R/out/$p/pipeline.log ] && cp $R/out/$p/pipeline.log $T/$p/
  [ -e $R/uploaded/$p ] || (cd $C/state 2>/dev/null && tar -czf $T/$p/state-not-uploaded.tar.gz $p 2>/dev/null)
done
/usr/local/bin/x1k-long-status > $T/status.txt 2>&1
[ -f $X ] && cp $X $T/excluded.tsv
aws s3 cp $T/ $B/dataset-x1k/final-a/ --recursive --only-show-errors
ok=1
for f in $(cd $T && find . -type f | sed 's|^\./||'); do
  s=$(aws s3 ls $B/dataset-x1k/final-a/$f | awk '{print $3}')
  [ "$s" = "$(stat -c %s $T/$f)" ] || { ok=0; echo "size check failed: $f"; }
done
if [ $ok = 1 ] && [ $clean = 1 ]; then
  { echo "x1k long rows final $(date -u +%FT%TZ) on $(cat /sys/devices/virtual/dmi/id/board_asset_tag)"
    for p in $(cat $L/run.list); do echo "$p: $([ -e $L/$p/uploaded/$p ] && echo uploaded || echo "excluded ($(grep -P "^$p\t" $X | cut -f2 | cut -c1-120))"); $(grep 'census finished rc=' $T/$p/run.log | tail -1 | cut -c1-160)"; done
  } > $T/DONE
  aws s3 cp $T/DONE $B/dataset-x1k/final-a/DONE --only-show-errors && cp $T/DONE $E/final-a-DONE
  cat $T/DONE
  up=$(awk '{print int($1)}' /proc/uptime)
  if [ -e /home/ec2-user/NO_SHUTDOWN ] || [ -e /run/x1k-hold ] || [ "$up" -lt 3600 ]; then
    echo "no shutdown (NO_SHUTDOWN, /run/x1k-hold or up < 1 h)"
  else
    sync; echo "shutdown in 2 min (the instance terminates; the volumes stay)"; shutdown -h +2
  fi
else
  { echo "x1k long rows ALERT $(date -u +%FT%TZ): all units inactive, clean=$clean (a unit without 'census finished' or a project without upload and not in excluded.tsv), size check ok=$ok; no shutdown"; } > $T/ALERT
  aws s3 cp $T/ALERT $B/dataset-x1k/live-a/ALERT --only-show-errors; cat $T/ALERT
fi
EOF_x1k_long_finalize
[ "$(sha256sum $F.new | cut -d' ' -f1)" = $NEW ] || { echo "ABORT: new text sha256 differs"; rm -f $F.new; exit 1; }
bash -n $F.new
chmod 755 $F.new
if [ "$have" = $OLD ]; then cp -p $F /root/x1k-long-finalize.before-R5; fi
mv -f $F.new $F
echo "installed $F: sha256 $(sha256sum $F | cut -c1-16) (was $(echo $have | cut -c1-16)); bash -n OK"
diff /root/x1k-long-finalize.before-R5 $F || true
echo "finalize timer: $(systemctl is-active x1k-long-finalize.timer); units active: $(for p in $(cat $L/run.list); do systemctl is-active -q x1k-long@$p && echo -n "$p "; done)"
echo "R5 (machine A) done"
