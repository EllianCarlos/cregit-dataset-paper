#!/usr/bin/env bash
# D11-row-fail.sh, machine A (read-only, through scripts/a/ssm-a.sh): why the aws-sdk-rust unit failed:
# the R8 log after the last change, the unit status and journal, the run.log and pipeline.log tails.
set -uo pipefail
p=awslabs__aws-sdk-rust; L=/data/x1k-long; R=$(readlink -f $L/$p)
echo "== $(date -u +%FT%TZ)"
echo "--- R8 log (last 25 lines)"; tail -25 $L/rebalance.log
echo "--- ALERT file: $([ -e $L/rebalance.ALERT ] && cat $L/rebalance.ALERT || echo absent); NO_SHUTDOWN: $([ -e /home/ec2-user/NO_SHUTDOWN ] && echo set || echo absent)"
echo "--- unit"; systemctl status x1k-long@$p --no-pager 2>&1 | head -12
echo "--- journal"; journalctl -u x1k-long@$p --since '-2 hours' --no-pager 2>&1 | tail -15
echo "--- run.log"; tail -15 $R/logs/run.log
echo "--- pipeline.log"; tail -25 $R/out/$p/pipeline.log | cut -c1-220
echo "--- run.env JOBS: $(sed -n 's/^JOBS=//p' $R/run.env); .blame: $(find $R/out/$p/blame -name '*.blame' | wc -l)"
free -g | sed -n 2p; df -h /data2 | tail -1
