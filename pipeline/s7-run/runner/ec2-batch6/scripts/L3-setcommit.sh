set -uo pipefail
/usr/local/bin/census-batch6L-cregit --base; echo "gate rc=$?"; /usr/local/bin/census-batch6L-wait --decide-only | cut -c1-400
