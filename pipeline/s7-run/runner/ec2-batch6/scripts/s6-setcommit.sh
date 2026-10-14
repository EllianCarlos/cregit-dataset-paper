set -uo pipefail
/usr/local/bin/census-fed-workload batch6 --base || exit 1
/usr/local/bin/census-fed-feeder; echo "feeder rc=$?"; tail -n 5 /data/logs/fed-feeder.log 2>/dev/null | cut -c1-220
