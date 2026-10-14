# s2-pre.sh (prepend X=a|b): checks before the batch 5 install on a running batch 3 spot instance.
set -uo pipefail
echo "== pre $(date -u +%FT%TZ) $(cat /sys/devices/virtual/dmi/id/board_asset_tag) half $X"
got=$(sha256sum /usr/local/bin/census-b3-finalize | cut -d' ' -f1)
[ "$got" = 4be4f17f4b8acbe5da76459d777efebf9c413a464e04eaf689e781e71c29bd6e ] || [ -e /usr/local/bin/census-b3-finalize.orig-b3only ] || { echo "census-b3-finalize is not the expected version ($got)"; exit 1; }
. /etc/cregit-census/batch.env
for u in $(for p in $PARTS; do echo census-b3@$p.service; done) census-b3-finalize.service census-b3-watch.service census-b3-upload.timer census-b3-live.timer; do
  [ "$(systemctl show $u -p NeedDaemonReload --value)" = no ] || { echo "$u: NeedDaemonReload=yes; aborting"; exit 1; }; done
echo "NeedDaemonReload=no for all census-b3 units"
systemctl show $(for p in $PARTS; do echo census-b3@$p.service; done) census-b3-finalize.service -p Id -p ActiveState -p MainPID | paste - - - - | tr '\t' ' ' > /root/b5-pre-units.txt; cat /root/b5-pre-units.txt
[ -e /home/ec2-user/NO_SHUTDOWN ] && echo "NO_SHUTDOWN present"
tail -n 2 /data/logs/finalize.log 2>/dev/null
