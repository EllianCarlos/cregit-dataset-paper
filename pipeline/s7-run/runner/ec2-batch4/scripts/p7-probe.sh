set +e
date -u +%FT%TZ; uptime; cat /proc/pressure/cpu /proc/pressure/io | cut -c1-60
cat /run/census-batch4-guard.status; systemctl show census-batch4-guard.service -p Result --value
systemctl is-active census-batch4p1.service census-batch4p2.service census-batch4p3.service census-batch2.service census-batch3L.service | tr '\n' ' '; echo
for k in 1 2 3; do grep '♥' /data/logs/batch4p$k.log | tail -1 | cut -c1-220; done
grep '♥' /data/logs/batch2.log | tail -1 | cut -c1-220; grep '♥' /data/logs/batch3L.log | tail -1 | cut -c1-220
ps -eo stat= | cut -c1 | sort | uniq -c | tr '\n' ' '; echo
