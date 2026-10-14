set +e
L=$(ls -t /b4p1/ctp/state/net-snmp__net-snmp/logs/pipeline-2026*.log | head -1); echo "$L"; tail -25 "$L" | cut -c1-250
echo "--- later attempts:"; grep -h -e "net-snmp" -e peercoin /data/logs/batch4p1.log /data/logs/batch4p3.log | grep -v '♥' | tail -8 | cut -c1-200
