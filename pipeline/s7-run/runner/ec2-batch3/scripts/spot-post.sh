set -uo pipefail
census-b3-parts-init "$X"
systemctl daemon-reload
cat /etc/cregit-census/batch.env
/usr/local/bin/census-b3-check
echo "check rc=$?"
