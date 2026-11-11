#!/usr/bin/env bash
# B1-tvl-run.sh (the token-vs-line machine, root, through ssm-tvl.sh): starts the unit tvl-run (tools/tvl_unit.sh ->
# tvl_run.py): clones, TOM copies, 3 line blames, measure, leak scan, upload of each project; the tables at the
# end; then the machine shuts down (DONE: in 1 min; ALERT: after ALERT_HOLD_MIN min) and stops (L1 set the stop
# behavior). Log /data/tvl/unit.log and /data/tvl/log/run.log; results in s3://B/token-vs-line/run/<Name>/.
# EXPORTS="JOBS=.. CAP_H=.. NOSHUT=1 ALERT_HOLD_MIN=.." change the defaults of tvl.conf. A second start continues.
set -uo pipefail
IID=${TVL_IID:-$(cat /sys/devices/virtual/dmi/id/board_asset_tag)}
case "||" in
  *"|$IID|"*) echo "ABORT: $IID is not the token-vs-line machine"; exit 1 ;; esac
X=${TVL_X:-/data/tvl}; T=$X/tools
WANT_SUMS=fcb5325676a472b076a2c825f09494ab003824db44448c4e5b9abfc6cd90afff
[ "$WANT_SUMS" != none ] || { echo "ABORT: no stage pin (S1 first)"; exit 1; }
[ "$(sha256sum $T/SHA256SUMS | cut -d' ' -f1)" = $WANT_SUMS ] || { echo "ABORT: tools SHA256SUMS is not ${WANT_SUMS:0:12} (run R1-tvl-setup.sh)"; exit 1; }
(cd $T && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: a tool sha256"; exit 1; }
[ -x $X/venv/bin/python ] || { echo "ABORT: no venv (R1 first)"; exit 1; }
grep -q "OK" $X/test-fixture.txt 2>/dev/null || { echo "ABORT: no fixture test pass (R1 first)"; exit 1; }
tok=$(curl -s -X PUT -H "X-aws-ec2-metadata-token-ttl-seconds: 60" http://169.254.169.254/latest/api/token)
export TVL_ITYPE=$(curl -s -H "X-aws-ec2-metadata-token: $tok" http://169.254.169.254/latest/meta-data/instance-type)
export KIT_SUMS=$WANT_SUMS X T TVL_RUN
bash $T/tvl_start.sh
