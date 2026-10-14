X=b
# s2-post.sh (after s5-files-1/2): daemon-reload (census-b3 units unchanged), inputs, parts, check.
set -uo pipefail
systemctl daemon-reload
. /etc/cregit-census/batch.env
systemctl show $(for p in $PARTS; do echo census-b3@$p.service; done) census-b3-finalize.service -p Id -p ActiveState -p MainPID | paste - - - - | tr '\t' ' ' > /root/b5-post-units.txt
cmp -s /root/b5-pre-units.txt /root/b5-post-units.txt && echo "census-b3 units: same state and MainPID after the daemon-reload" || { echo "census-b3 units changed:"; diff /root/b5-pre-units.txt /root/b5-post-units.txt; }
systemctl show census-b5@x.service -p OOMPolicy -p RequiresMountsFor -p OnSuccess | tr '\n' ' '; echo
echo "== prep"; /usr/local/bin/census-b5-prep $X || exit 1
echo "== parts"; t0=$(date +%s); /usr/local/bin/census-b5-parts-init $X || exit 1; echo "parts-init took $(( $(date +%s) - t0 )) s"
echo "== check"; /usr/local/bin/census-b5-check; echo "check rc=$?"
cat /etc/cregit-census/s5/batch.env
