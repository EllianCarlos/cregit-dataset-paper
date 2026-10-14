#!/usr/bin/env bash
# W1-watch-entries.sh (this machine; 2026-10-12): add census L1r (batch 1 rerun, L) to the local watchdog,
# status_all.sh and fetch_done.sh. Each file is edited through a temp file and an atomic mv (a timer may
# read it at any time); the old watchdog is kept as watchdog.sh.orig-L1r and the new one gets mode 755.
# It refuses if a file does not hold the expected line (another edit came first: do it by hand).
# Before the L1r install the watchdog only logs "L1r: no live status" (no alert).
set -euo pipefail
WD=$HOME/s3-work/census-watchdog/watchdog.sh
S7=${RUNNER_PROJECTS}/${RUNNER_STUDY_REPO}/2026.2-estudos-pesquisa-sistemas/dataset-selection/s7-run
edit() {  # FILE OLD NEW
  local f=$1 old=$2 new=$3 t
  NEW=$new python3 -I -c 'import os, sys; sys.exit(os.environ["NEW"] not in open(sys.argv[1]).read())' "$f" && { echo "$f: already has the L1r line"; return 0; }
  [ "$(grep -cF -- "$old" "$f")" = 1 ] || { echo "ABORT: $f does not hold exactly one line: $old"; exit 1; }
  t=$(mktemp "$f.XXXX"); OLD=$old NEW=$new python3 -I -c '
import os, sys
s = open(sys.argv[1]).read(); o, n = os.environ["OLD"], os.environ["NEW"]
assert s.count(o) == 1
open(sys.argv[2], "w").write(s.replace(o, n))' "$f" "$t"
  bash -n "$t" || { rm -f "$t"; echo "ABORT: $f syntax"; exit 1; }
  chmod --reference="$f" "$t"; mv -f "$t" "$f"; echo "$f: L1r added"
}
[ -e $WD.orig-L1r ] || cp -p $WD $WD.orig-L1r
edit $WD 'for run in batch2 batch3L batch4 batch5L batch6L L7-20 L22 L7-20b L23; do' \
         'for run in batch2 batch3L batch4 batch5L batch6L L7-20 L22 L7-20b L23 L1r; do'
chmod 755 $WD
edit $S7/status_all.sh 'for run in batch2 batch3L batch3/a batch3/b batch4 batch5L batch6L L7-20 L22 L7-20b L23 batch5/a1' \
         'for run in batch2 batch3L batch3/a batch3/b batch4 batch5L batch6L L7-20 L22 L7-20b L23 L1r batch5/a1'
edit $S7/status_all.sh '# batch 2 instance; its "split:" line is the watcher that stops L7-20 before row 17.' \
         '# batch 2 instance; its "split:" line is the watcher that stops L7-20 before row 17.
# L1r: the batch 1 rerun of torvalds__linux and SAP__project-foxhound (2 workers, cregit 57551d7) on the
# batch 2 instance; its waiter holds the start ("waiting") until census L23 has started.'
edit $S7/fetch_done.sh '$(seq -f "batch%g" -s " " 7 23) L7-20 L22 L7-20b L23"}' \
         '$(seq -f "batch%g" -s " " 7 23) L7-20 L22 L7-20b L23 L1r"}'
echo "done; the watchdog checks L1r from its next pass (a missing live status is only logged)"
