# read-only: disk growth and DuckDB temp spill of the step-10 processes (2026-10-14)
for i in 1 2 3 4; do
  echo "== $(date -u +%T) data=$(df -BG --output=avail /data | tail -1) bL7=$(df -BG --output=avail /bL7 | tail -1) bL7b=$(df -BG --output=avail /bL7b | tail -1) bL23=$(df -BG --output=avail /bL23 | tail -1)"
  for f in $(ls -d /bL7/census-2026-10-L7-20/*/ /bL7b/census-2026-10-L7-20b/*/ 2>/dev/null); do
    s=$(find $f -maxdepth 2 -name 'duckdb_temp_storage*' -printf '%s\n' 2>/dev/null | awk '{t+=$1} END{printf "%.0f", t/1e9}')
    [ "${s:-0}" -gt 0 ] && echo "   $(basename $f) duckdb_temp ${s}G"
  done
  [ $i -lt 4 ] && sleep 100
done
pgrep -a -f generate_dataset[.]py | cut -c1-160
