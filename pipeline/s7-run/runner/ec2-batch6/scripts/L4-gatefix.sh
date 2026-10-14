set -uo pipefail
ls -ld /etc/cregit-census 2>&1; mkdir -p /etc/cregit-census && chmod 755 /etc/cregit-census
/usr/local/bin/census-batch6L-cregit --base; echo "gate rc=$?"
tail -3 /etc/cregit-census/batch6L.gate
/usr/local/bin/census-batch6L-wait --decide-only | cut -c1-400
