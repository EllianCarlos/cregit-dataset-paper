#!/usr/bin/env bash
# B1-tom5-run.sh (the TOM-5 machine, root, through ssm-tom5.sh): starts the unit tom5-run = tools/tom5_run.sh: preflight,
# fetch, newlist, shape, footfix, footers, license, ledger, pseudo, fetch2, base, plan, canary, pass, assemble, tables, manifest,
# markers, checksums, view, checks, upload, hf, end (tom5_run.sh says each step). Log /data/tom5/run.log, logs in
# s3://B/dataset-release/dataset-v1.0.0-tom-5/log/. At the end the instance shuts down (DONE: at once; ALERT: after
# ALERT_HOLD_MIN minutes) and stops (L1 set the stop behavior).
# EXPORTS="JOBS=.. HF=0 NOSHUT=1 ALERT_HOLD_MIN=.. HF_PRE_VERIFY=skip ETAG_CHECK=report" change the defaults of
# tom5.conf. A second start after an ALERT continues (the DONE steps and the files of the pass with an OK ledger line
# are skipped).
set -uo pipefail
IID=${TOM_IID:-$(cat /sys/devices/virtual/dmi/id/board_asset_tag)}
case "|REFUSED_INSTANCE_IDS|" in
  *"|$IID|"*) echo "ABORT: $IID is not the TOM-5 machine"; exit 1 ;; esac
X=${TOM_X:-/data/tom5}; T=$X/tools
WANT_SUMS=da9125463a33d480755cdcb9ec91f6a6fab8292d4e73667785c1d3ed12fb43f6
[ "$WANT_SUMS" != none ] || { echo "ABORT: no stage pin (S1 first)"; exit 1; }
[ "$(sha256sum $T/SHA256SUMS | cut -d' ' -f1)" = $WANT_SUMS ] || { echo "ABORT: tools SHA256SUMS is not ${WANT_SUMS:0:12} (run R1-tom5-setup.sh)"; exit 1; }
(cd $T && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: a tool sha256"; exit 1; }
[ -x $X/venv/bin/python ] || { echo "ABORT: no venv (R1 first)"; exit 1; }
bash $T/tom5_start.sh
