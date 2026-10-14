set -uo pipefail
FED=/etc/cregit-census/fed
echo 5 > $FED/slots.new && mv -f $FED/slots.new $FED/slots
echo 16 > $FED/worker_slots.new && mv -f $FED/worker_slots.new $FED/worker_slots
echo "PAUSE was: $(cat $FED/PAUSE 2>/dev/null)"; rm -f $FED/PAUSE
df -h /data1 /data2 /data3 /data4 | cut -c1-80
free -g | head -2
/usr/local/bin/census-fed-feeder; echo "feeder rc=$?"
tail -2 /data/logs/fed-feeder.log | cut -c1-200
systemctl list-units "census-fed@*" "census-b5@*" --no-legend --no-pager | cut -c1-60
