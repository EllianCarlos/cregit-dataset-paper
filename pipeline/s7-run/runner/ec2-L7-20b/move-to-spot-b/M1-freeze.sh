# M1 (2026-10-13, user decision "move the not-started L7-20b rows to spot b"): touch /bL7b/ctp/STOP so
# census L7-20b starts no new row. Running rows finish. Not latched: removing STOP resumes starts.
set -euo pipefail
date -u +%FT%TZ
st=/bL7b/ctp/state
echo "running/started rows (state dirs):"; ls $st | sort
[ -e /bL7b/ctp/STOP ] && echo "STOP already present" || { install -o ec2-user -g ec2-user -m 644 /dev/null /bL7b/ctp/STOP; echo "STOP written"; }
echo "user decision 2026-10-13: not-started rows move to spot b" > /bL7b/ctp/STOP.move-to-spot-b
chown ec2-user:ec2-user /bL7b/ctp/STOP.move-to-spot-b
ls -l /bL7b/ctp/STOP*
sleep 20; ls $st | sort | md5sum; ls $st | wc -l
systemctl is-active census-L7-20b
tail -3 /data/logs/L7-20b.log
