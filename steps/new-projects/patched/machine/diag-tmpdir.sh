#!/bin/bash
pid=$(systemctl show -p MainPID --value ta-run 2>/dev/null)
echo "ta-run state: $(systemctl is-active ta-run 2>/dev/null) pid=$pid cwd=$( [ "$pid" != 0 ] && readlink /proc/$pid/cwd )"
for d in / /data/ta; do install -d -m 0700 -o ec2-user -g ec2-user "${d%/}/.tmp" && echo "made ${d%/}/.tmp"; done
ls -ld /.tmp /data/ta/.tmp; cat /data/ta/sums.patched 2>/dev/null | cut -c1-12
