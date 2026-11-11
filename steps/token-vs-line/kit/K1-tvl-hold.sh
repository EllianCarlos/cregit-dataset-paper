#!/usr/bin/env bash
# K1-tvl-hold.sh (the token-vs-line machine, root, through ssm-tvl.sh with EXPORTS="ACTION=..."): the end of the run.
#   ACTION=hold     touch /run/tvl-hold and cancel a scheduled shutdown (also the backstop at the run cap: the
#                   machine stays up; look, then ACTION=stop-now). The hold file is in tmpfs: a reboot clears it.
#   ACTION=unhold   remove /run/tvl-hold (no new shutdown is scheduled: use stop or stop-now)
#   ACTION=stop     touch /data/tvl/STOP: the blames stop now, as at the run cap (started projects are measured
#                   with what they have, the tables are uploaded, then the machine shuts down)
#   ACTION=stop-now shutdown -h now (the instance stops: L1 set the stop behavior; no upload of open work)
set -uo pipefail
IID=${TVL_IID:-$(cat /sys/devices/virtual/dmi/id/board_asset_tag)}
case "||" in
  *"|$IID|"*) echo "ABORT: $IID is not the token-vs-line machine"; exit 1 ;; esac
X=${TVL_X:-/data/tvl}
case ${ACTION:-} in
  hold) touch /run/tvl-hold; [ -f /run/systemd/shutdown/scheduled ] && shutdown -c; echo "held; tvl-run: $(systemctl is-active tvl-run)" ;;
  unhold) rm -f /run/tvl-hold; echo "hold removed" ;;
  stop) touch $X/STOP; echo "STOP file set (the run ends within 1 min of blames, then measures and uploads)" ;;
  stop-now) echo "shutdown now (stop)"; shutdown -h now ;;
  *) echo "ABORT: ACTION is hold, unhold, stop or stop-now"; exit 1 ;;
esac
