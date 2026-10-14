# M2 (read-only): before the batch24 enqueue on spot b, check that L7-20b still holds its STOP
date -u +%FT%TZ
ls -l /bL7b/ctp/STOP /bL7b/ctp/STOP.move-to-spot-b
ls /bL7b/ctp/state | wc -l
systemctl is-active census-L7-20b
tail -1 /data/logs/L7-20b.log | cut -c1-300
