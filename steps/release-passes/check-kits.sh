#!/usr/bin/env bash
# check-kits.sh: check the copies of the release pass kits against the staged lists.
#
# Usage: steps/release-passes/check-kits.sh
# - Each row of PASS/SHA256SUMS (the staged list of the run) must have a row in KITS.tsv with
#   the same sha256, and KITS.tsv must have no other row for that pass.
# - Each copy of KITS.tsv must have its copy_sha256. A copy must have the staged sha256, except
#   the rows whose note says which value was replaced.
# - PASS/SHA256SUMS must have the sha256 of the staged list (the row SHA256SUMS of KITS.tsv).
# - A pass name of KITS.tsv that is not in the list below (pass-5-integrity) has no staged list:
#   only its copies are checked.
# It needs no network and no data outside this repository.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
top=$(cd "$here/../.." && pwd)
kits=$here/KITS.tsv
fail=0
for p in pass-1 pass-2 pass-3 pass-4-doi pass-5-revision; do
  want=$(awk -F'\t' -v p="$p" '$1 == p && $2 != "SHA256SUMS" { print $3 "  " $2 }' "$kits" | sort)
  got=$(sort "$here/$p/SHA256SUMS")
  if [ "$want" = "$got" ]; then
    echo "OK   $p: $(wc -l < "$here/$p/SHA256SUMS") staged rows in KITS.tsv"
  else
    echo "FAIL $p: KITS.tsv and $p/SHA256SUMS differ"; fail=1
  fi
done
while IFS=$'\t' read -r pass name staged copy copy_sha note; do
  [ "$pass" = pass ] && continue
  [ "$copy" = - ] && continue
  if [ ! -f "$top/$copy" ]; then echo "FAIL $pass $name: no copy $copy"; fail=1; continue; fi
  got=$(sha256sum "$top/$copy" | cut -c1-64)
  if [ "$got" != "$copy_sha" ]; then
    echo "FAIL $pass $name: $copy has sha256 $got, want $copy_sha"; fail=1
  elif [ "$copy_sha" != "$staged" ] && [ "${note#*replaced}" = "$note" ]; then
    echo "FAIL $pass $name: the copy differs from the staged file and the note gives no reason"; fail=1
  fi
done < "$kits"
n=$(awk -F'\t' 'NR > 1 && $4 != "-"' "$kits" | wc -l)
[ "$fail" -eq 0 ] && echo "OK: the $n copies of KITS.tsv match their sha256"
exit "$fail"
