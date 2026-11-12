#!/usr/bin/env bash
# B2-tom6-run-corrected.sh (the TOM-6 machine, root, through ssm-tom6.sh): starts the unit tom6-run = tools/tom6_run.sh: preflight,
# B2: as B1, but the file inputs/corrections.tsv may differ from the stage (P2 put the hand-set license value); SHA256SUMS itself is still pinned.
# fetch, newlist, shape, footfix, footers, license, ledger, pseudo, fetch2, base, plan, canary, pass, assemble, tables, manifest,
# markers, checksums, view, checks, upload, hf, end (tom6_run.sh says each step). Log /data/tom6/run.log, logs in
# s3://B/dataset-release/dataset-v1.1.0/log/. At the end the instance shuts down (DONE: at once; ALERT: after
# ALERT_HOLD_MIN minutes) and stops (L1 set the stop behavior).
# EXPORTS="JOBS=.. HF=0 NOSHUT=1 ALERT_HOLD_MIN=.. HF_PRE_VERIFY=skip ETAG_CHECK=report" change the defaults of
# tom6.conf. A second start after an ALERT continues (the DONE steps and the files of the pass with an OK ledger line
# are skipped).
set -uo pipefail
IID=${TOM_IID:-$(cat /sys/devices/virtual/dmi/id/board_asset_tag)}
case "|REFUSED_INSTANCE_IDS|" in
  *"|$IID|"*) echo "ABORT: $IID is not the TOM-6 machine"; exit 1 ;; esac
X=${TOM_X:-/data/tom6}; T=$X/tools
WANT_SUMS=086d54a1cedb8a6d6287e17a1f5408cf3c0a3481375c057a0b98be39f297123d
[ "$WANT_SUMS" != none ] || { echo "ABORT: no stage pin (S1 first)"; exit 1; }
[ "$(sha256sum $T/SHA256SUMS | cut -d' ' -f1)" = $WANT_SUMS ] || { echo "ABORT: tools SHA256SUMS is not ${WANT_SUMS:0:12} (run R1-tom6-setup.sh)"; exit 1; }
(cd $T && grep -v "  inputs/corrections.tsv$" SHA256SUMS | sha256sum --quiet -c -) || { echo "ABORT: a tool sha256"; exit 1; }
[ -x $X/venv/bin/python ] || { echo "ABORT: no venv (R1 first)"; exit 1; }
bash $T/tom6_start.sh
