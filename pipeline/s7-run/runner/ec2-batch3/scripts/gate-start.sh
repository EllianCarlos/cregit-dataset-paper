# gate-start.sh: parts, the identity check as a gate, then the census.
set -uo pipefail
census-b3-parts-init "$X" || exit 1
systemctl daemon-reload
/usr/local/bin/census-b3-check > /data/logs/check-gate.log 2>&1
grep -E 'libsrcml.so.1.1.0 sha256|libexpat Parquet sha256|CHECK' /data/logs/check-gate.log
grep -q '^CHECK OK' /data/logs/check-gate.log || { echo "IDENTITY CHECK FAILED: census not started"; exit 1; }
/usr/local/bin/census-b3-start
