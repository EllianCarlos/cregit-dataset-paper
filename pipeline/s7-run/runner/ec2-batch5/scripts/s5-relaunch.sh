# s5-relaunch.sh (prepend X=a|b; run by restart_spot.sh on a relaunched spot instance after the
# s5 files): the batch5 / batch1rest parts of the half with work left: inputs and run manifests
# (minus done/OK), parts (own loop XFS, ctp clone, cregit copy per part), identity check on one new
# copy (the census does not start if it fails), start.
set -uo pipefail
/usr/local/bin/census-b5-prep $X || exit 1
/usr/local/bin/census-b5-parts-init $X || exit 1
systemctl daemon-reload
/usr/local/bin/census-b5-check || { echo "IDENTITY CHECK FAILED: batch5 parts not started"; exit 1; }
/usr/local/bin/census-b5-start
