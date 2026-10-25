#!/usr/bin/env bash
# D2-noblame-detail.sh (machine B or A, read-only, through ssm.sh / ssm-a.sh): for each row with a pipeline
# log that ends in "no .blame files found", print steps 6-8 of the newest pipeline log and what the
# pinned clone holds at the pinned commit (files that match the language filter of ctp, by extension).
# Use: I=<id> TAILN=400 bash scripts/ssm.sh scripts/D2-noblame-detail.sh 300
set -uo pipefail
RX='\.(c|c\+\+|cc|cp|cpp|cxx|h|h\+\+|hh|hpp|hxx|java|rs|tcc)$'
for L in $(ls -d /data[1-4]/x1k/ctp/state/*/logs /data[1-4]/x1k/*/ctp/state/*/logs 2>/dev/null); do
  last=$(ls -t $L/pipeline-2*.log 2>/dev/null | head -1)
  [ -n "$last" ] && grep -q 'no .blame files found' "$last" || continue
  p=$(basename "$(dirname "$L")"); root=${L%%/ctp/state/*}
  echo "=== $p ($last)"
  awk '/Step 6 /{f=1} /Step 9 /{f=0} f' "$last" | cut -c1-260 | head -40
  g=$(ls -d $root/out/.ctp-pinned/$p.git 2>/dev/null | head -1)
  if [ -n "$g" ]; then
    sha=$(git -c safe.directory="*" -C "$g" rev-parse HEAD 2>/dev/null)
    n=$(git -c safe.directory="*" -C "$g" ls-tree -r --name-only HEAD 2>/dev/null | wc -l)
    m=$(git -c safe.directory="*" -C "$g" ls-tree -r --name-only HEAD 2>/dev/null | grep -i -c -E "$RX")
    echo "  pinned clone HEAD $sha: $n files, $m match the filter"
    git -c safe.directory="*" -C "$g" ls-tree -r --name-only HEAD 2>/dev/null | grep -i -E "$RX" | head -5 | sed 's/^/    /'
    echo "  extensions at HEAD (top 8): $(git -c safe.directory="*" -C "$g" ls-tree -r --name-only HEAD 2>/dev/null | sed -n 's/.*\.\([A-Za-z0-9+]*\)$/\1/p' | sort | uniq -c | sort -rn | head -8 | tr -s ' ' | tr '\n' ' ')"
    echo "  quoted (non-ASCII) paths at HEAD: $(git -c safe.directory="*" -C "$g" ls-tree -r --name-only HEAD 2>/dev/null | grep -c '^"'); matching after unquote: $(git -c safe.directory="*" -c core.quotePath=false -C "$g" ls-tree -r --name-only HEAD 2>/dev/null | grep -i -c -E "$RX")"
    echo "  matching paths in all history: $(git -c safe.directory="*" -C "$g" log --all --name-only --format= 2>/dev/null | grep -i -E "$RX" | sort -u | wc -l)"
  else
    echo "  no pinned clone"
  fi
done
exit 0
