#!/usr/bin/env bash
# M9-last.sh (spot a, read-only): the project that still runs and its output size.
R=/data1/v1raw
comm -23 <(tail -n +2 $R/inputs.tsv | cut -f1 | sort) <(tail -n +2 $R/out/results.tsv | cut -f1 | sort)
ls -la $R/out/parquet/.*tmp* $R/out/parquet/*.tmp* 2>/dev/null | tail -3
find /data1/v1raw/out/parquet /data2/v1raw-work -newer $R/out/results.tsv -type f -printf '%TT %s %p\n' 2>/dev/null | tail -5
grep -c . $R/out/merge.log; ps -eo pid,etime,pcpu,rss,args | grep -v grep | grep rewrite_meta | cut -c1-200
