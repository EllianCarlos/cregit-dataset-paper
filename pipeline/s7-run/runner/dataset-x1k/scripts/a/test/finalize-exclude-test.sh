#!/usr/bin/env bash
# finalize-exclude-test.sh (local): runs a finalize text (arg 1) against a fake machine A with fake aws,
# systemctl, sudo and shutdown. 11 rows: 9 uploaded, neuro-book and blue_archive failed (census finished rc=1).
# Cases: (1) excluded.tsv lists the 2 -> DONE + shutdown; (2) no excluded.tsv -> ALERT; (3) only 1 listed
# -> ALERT; (4) a unit is active -> nothing. Use: bash finalize-exclude-test.sh <finalize text> [expect-old]
set -uo pipefail
src=$(readlink -f "${1:?finalize text}"); old=${2:-}
W=$(mktemp -d); trap 'rm -r "$W"' EXIT
mkdir -p $W/bin
N=0
cat > $W/bin/aws <<EOF
#!/usr/bin/env bash
# fake aws: s3 cp (file or --recursive dir) into <case dir>/s3; s3 ls prints "date time size name"
[ "\$1" = s3 ] || exit 1
k() { echo "\$(cat $W/s3root)/\${1#s3://}"; }
case \$2 in
  cp) if [ "\$5" = --recursive ] || [ "\${5:-}" = --recursive ] || [ "\${4:-}" = --recursive ]; then mkdir -p "\$(k \$4)"; cp -r "\$3"/. "\$(k \$4)"/;
      else mkdir -p "\$(dirname "\$(k \$4)")"; cp "\$3" "\$(k \$4)"; fi ;;
  ls) f=\$(k \$3); [ -f "\$f" ] && echo "2026-10-20 00:00:00 \$(stat -c %s "\$f") \$(basename "\$f")" ;;
esac
EOF
cat > $W/bin/systemctl <<EOF
#!/usr/bin/env bash
# fake systemctl is-active -q x1k-long@<p>: active only for the name in <case dir>/active
A=\$(cat $W/cur)/active; [ "\$1" = is-active ] && [ -f \$A ] && [ "\${3#x1k-long@}" = "\$(cat \$A)" ] && exit 0
exit 3
EOF
printf '#!/usr/bin/env bash\nshift 2; "$@"\n' > $W/bin/sudo
printf '#!/usr/bin/env bash\necho "FAKE shutdown $*" >> "$(cat %s/cur)/shutdown.log"\n' "$W" > $W/bin/shutdown
chmod 755 $W/bin/*
rows="RMerl__asuswrt-merlin.ng awslabs__aws-sdk-rust notnotype__neuro-book pur1fying__blue_archive_auto_script aws__aws-sdk-java TencentCloud__tencentcloud-sdk-cpp metashell__metashell googleapis__google-cloud-rust Byron__google-apis-rs microsoftgraph__msgraph-beta-sdk-java autc04__Retro68"
setup() {
  N=$((N+1)); C=$W/c$N; mkdir -p $C/s3; echo $C > $W/cur; echo $C/s3 > $W/s3root
  L=$C/m/x1k-long; E=$C/m/etc; mkdir -p $L $E; D=$C/s3/${RUNNER_BUCKET}/dataset-x1k
  echo "started test" > $L/started; : > $L/run.list
  for p in $rows; do R=$C/m/data/x1k/$p; mkdir -p $R/ctp/state/$p $R/logs $R/uploaded $R/out/$p; ln -s $R $L/$p
    echo $p >> $L/run.list; echo '{}' > $R/ctp/ledger.jsonl; echo "m" > $R/manifest.tsv; echo "e" > $R/run.env
    case $p in notnotype__neuro-book|pur1fying__blue_archive_auto_script)
      echo "[12:44:05] census finished rc=1: failed 1" > $R/logs/run.log ;;
    *) echo "[20:00:00] census finished rc=0: done 1" > $R/logs/run.log; echo ok > $R/uploaded/$p ;; esac
  done
  echo i-test > $C/m/asset; echo "99999.0 1.0" > $C/m/uptime
  sed -e "s|E=/etc/dataset-x1k; L=/data/x1k-long|E=$E; L=$L|" -e "s|/usr/local/bin/x1k-long-upload|true|" \
      -e "s|/usr/local/bin/x1k-long-status|echo status|" -e "s|/sys/devices/virtual/dmi/id/board_asset_tag|$C/m/asset|" \
      -e "s|/proc/uptime|$C/m/uptime|" -e "s|/home/ec2-user/NO_SHUTDOWN|$C/m/NO_SHUTDOWN|" -e "s|/run/x1k-|$C/m/run-x1k-|g" \
      "$src" > $W/fin; bash -n $W/fin
}
X='notnotype__neuro-book	no tokens: 0 C/C++/Java/Rust files at the pinned commit (step 10: no .blame files found)
pur1fying__blue_archive_auto_script	no tokens: 0 C/C++/Java/Rust files at the pinned commit (step 10: no .blame files found)'
run() { PATH=$W/bin:$PATH bash $W/fin > $W/out 2>&1; echo "rc=$?"; }
fail=0; chk() { if eval "$2"; then echo "  PASS $1"; else echo "  FAIL $1"; fail=1; sed 's/^/    | /' $W/out; fi; }
echo "case 1: excluded.tsv lists the 2 rows"; setup; printf '%s\n' "$X" > $L/excluded.tsv; run
if [ -n "$old" ]; then chk "old text: ALERT, no DONE" "[ -f $D/live-a/ALERT ] && [ ! -f $D/final-a/DONE ]"
else
  chk "final-a/DONE in fake S3" "[ -f $D/final-a/DONE ]"
  chk "DONE has 9 uploaded + 2 excluded" "[ \$(grep -c ': uploaded;' $D/final-a/DONE) = 9 ] && [ \$(grep -c ': excluded (no tokens' $D/final-a/DONE) = 2 ]"
  chk "final-a/excluded.tsv equal" "cmp -s $L/excluded.tsv $D/final-a/excluded.tsv"
  chk "shutdown called" "grep -q 'FAKE shutdown -h +2' $C/shutdown.log"
  chk "no ALERT" "[ ! -f $D/live-a/ALERT ]"
  chk "local final-a-DONE" "[ -f $E/final-a-DONE ]"
  sed 's/^/    DONE| /' $D/final-a/DONE
fi
echo "case 2: no excluded.tsv"; setup; run
chk "ALERT, no DONE, no shutdown" "[ -f $D/live-a/ALERT ] && [ ! -f $D/final-a/DONE ] && [ ! -f $C/shutdown.log ]"
echo "case 3: only neuro-book listed"; setup; printf '%s\n' "$X" | head -1 > $L/excluded.tsv; run
chk "ALERT, no DONE, no shutdown" "[ -f $D/live-a/ALERT ] && [ ! -f $D/final-a/DONE ] && [ ! -f $C/shutdown.log ]"
echo "case 4: a unit active"; setup; printf '%s\n' "$X" > $L/excluded.tsv; echo awslabs__aws-sdk-rust > $C/active; run
chk "nothing written, no shutdown" "[ -z \"\$(ls -A $C/s3)\" ] && [ ! -f $C/shutdown.log ]"
echo "case 5: excluded row unit without 'census finished'"; setup; printf '%s\n' "$X" > $L/excluded.tsv; : > $C/m/data/x1k/notnotype__neuro-book/logs/run.log; run
chk "ALERT, no shutdown" "[ -f $D/live-a/ALERT ] && [ ! -f $C/shutdown.log ]"
[ $fail = 0 ] && echo "FINALIZE TEST OK" || { echo "FINALIZE TEST FAILED"; exit 1; }
