set +e
for k in 1 2 3; do echo "--- p$k"; awk '/census-batch4p'$k' start/ {n=NR} END{}' /data/logs/batch4p$k.log; sed -n "$(grep -n "census-batch4p$k start" /data/logs/batch4p$k.log | tail -1 | cut -d: -f1),\$p" /data/logs/batch4p$k.log | grep -v '♥' | grep -e census: -e net-snmp -e CrispASR -e verovio -e acrn-libvirt -e camel-spring -e kitty -e peercoin -e "to run" | head -12 | cut -c1-220; done
