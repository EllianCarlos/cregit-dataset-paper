set -uo pipefail
B=/usr/local/bin
cat > $B/cregit-L7-20-v2swap.new <<'EOF_cregit-L7-20-v2swap'
#!/usr/bin/env bash
# cregit-L7-20-v2swap (cregit-L7-20-v2swap.timer, root, every 2 min; 2026-10-10 ~02:55 UTC): put the v2
# inputs of census L7-20 (batch 21's NetBSD__pkgsrc added) in place before the census starts.
# The L7-20 waiter is held by /bL7/ctp/STOP with the marker /bL7/ctp/STOP.v2-hold. Each pass: if
# s3://BUCKET/L7-20/input/SHA256SUMS has the v2 sha256 (the user ran ~/s3-work/upload-L7-20-v2.sh), copy
# L7-20/input/ to a temp dir as ec2-user, check every sha256, move any older inputs in
# /home/ec2-user/L7-20-input/ aside (v1.<time>/), move the v2 files in, then remove the marker and the
# STOP (the STOP stays if the disk guard has tripped), and stop this timer. Refuses if census-L7-20 runs.
set -uo pipefail
export AWS_PAGER=""
EXP=bfa9fae7123f4bbaaf9c216e74c058a3cdf8a78431d7d7f446d18e642a7ac481
B=s3://${RUNNER_BUCKET}; IN=/home/ec2-user/L7-20-input; ST=/run/cregit-L7-20-v2swap.status
say() { echo "$(date -u +%FT%TZ) $*" | tee $ST; }
[ -e /bL7/ctp/STOP.v2-hold ] || { say "no hold marker: nothing to do"; systemctl stop --no-block cregit-L7-20-v2swap.timer; exit 0; }
case $(systemctl is-active census-L7-20.service) in active|activating) say "census-L7-20 is active: not swapping"; exit 1 ;; esac
got=$(aws s3 cp $B/L7-20/input/SHA256SUMS - 2>/dev/null | sha256sum | cut -d' ' -f1)
[ "$got" = "$EXP" ] || { say "waiting for the v2 upload (S3 SHA256SUMS sha256 ${got:0:16}, want ${EXP:0:16})"; exit 0; }
T=$(sudo -u ec2-user mktemp -d /home/ec2-user/L7-20-input.v2.XXXX)
sudo -u ec2-user bash -c "AWS_PAGER= aws s3 cp $B/L7-20/input/ $T/ --recursive --only-show-errors && cd $T && sha256sum --quiet -c SHA256SUMS" || { say "v2 copy or check FAILED"; exit 1; }
[ "$(sha256sum $T/SHA256SUMS | cut -d' ' -f1)" = "$EXP" ] || { say "v2 SHA256SUMS changed during the copy"; exit 1; }
old=$IN/v1.$(date +%s); mkdir -p $IN
for f in manifest.L7-20.tsv project_meta.L7-20.json SHA256SUMS; do [ -e $IN/$f ] && { mkdir -p $old; mv $IN/$f $old/; }; done
for f in manifest.L7-20.tsv project_meta.L7-20.json SHA256SUMS; do mv $T/$f $IN/$f; done
chown -R ec2-user: $IN; rmdir $T 2>/dev/null
(cd $IN && sha256sum --quiet -c SHA256SUMS) || { say "v2 inputs do not check in $IN"; exit 1; }
n=$(grep -c -v -e '^#' -e '^[[:space:]]*$' $IN/manifest.L7-20.tsv)
rm -f /bL7/ctp/STOP.v2-hold
if [ -e /run/census-batch4-guard.tripped ]; then say "v2 inputs in place ($n projects); the disk guard has tripped, so /bL7/ctp/STOP stays"
else rm -f /bL7/ctp/STOP; say "v2 inputs in place ($n projects, SHA256SUMS ${EXP:0:16}); hold lifted: STOP removed"; fi
systemctl stop --no-block cregit-L7-20-v2swap.timer
EOF_cregit-L7-20-v2swap
chmod 755 $B/cregit-L7-20-v2swap.new; mv -f $B/cregit-L7-20-v2swap.new $B/cregit-L7-20-v2swap
cat > /etc/systemd/system/cregit-L7-20-v2swap.service.new <<'EOF_cregit-L7-20-v2swap.service'
[Unit]
Description=L7-20: put the v2 inputs in place (NetBSD/pkgsrc added) and lift the waiter hold

[Service]
Type=oneshot
ExecStart=/usr/local/bin/cregit-L7-20-v2swap
TimeoutStartSec=600
EOF_cregit-L7-20-v2swap.service
chmod 644 /etc/systemd/system/cregit-L7-20-v2swap.service.new; mv -f /etc/systemd/system/cregit-L7-20-v2swap.service.new /etc/systemd/system/cregit-L7-20-v2swap.service
cat > /etc/systemd/system/cregit-L7-20-v2swap.timer.new <<'EOF_cregit-L7-20-v2swap.timer'
[Unit]
Description=L7-20: check for the v2 inputs every 2 min

[Timer]
OnActiveSec=30s
OnUnitActiveSec=2min
AccuracySec=10s
EOF_cregit-L7-20-v2swap.timer
chmod 644 /etc/systemd/system/cregit-L7-20-v2swap.timer.new; mv -f /etc/systemd/system/cregit-L7-20-v2swap.timer.new /etc/systemd/system/cregit-L7-20-v2swap.timer
U=$(systemctl list-units --no-legend --plain --all 'census*' | awk '{print $1}')
for u in $U; do [ "$(systemctl show $u -p NeedDaemonReload --value)" = no ] || { echo "$u: NeedDaemonReload=yes; aborting"; exit 1; }; done
echo "NeedDaemonReload=no for all $(echo $U | wc -w) loaded census units"
R=$(systemctl list-units --no-legend --plain --state=active 'census*.service' | awk '{print $1}')
before=$(for u in $R; do echo "$u $(systemctl show $u -p MainPID -p ActiveEnterTimestamp --value | tr '\n' ' ')"; done)
systemctl daemon-reload
after=$(for u in $R; do echo "$u $(systemctl show $u -p MainPID -p ActiveEnterTimestamp --value | tr '\n' ' ')"; done)
[ "$before" = "$after" ] && echo "running census units unchanged by the reload ($(echo "$R" | grep -c .))" || { echo CHANGED; diff <(echo "$before") <(echo "$after"); }
$B/cregit-L7-20-v2swap; echo "swap pass rc=$?"
systemctl start cregit-L7-20-v2swap.timer; echo "timer: $(systemctl is-active cregit-L7-20-v2swap.timer)"
echo "waiter: $(cut -c1-80 /run/census-L7-20-wait.status) ... $(sed 's/.*;//' /run/census-L7-20-wait.status)"
