#!/usr/bin/env bash
# M0-probe.sh (spot a, read-only): the Python with duckdb for the v1-raw merge; validate_schema.py sha256; disks.
set -uo pipefail
echo "== $(date -u +%FT%TZ) $(cat /sys/devices/virtual/dmi/id/board_asset_tag)"
for d in /w/batch13a1/ctp /data/ctp /home/ec2-user/ctp; do
  [ -x $d/.venv/bin/python ] && echo "$d/.venv: $(runuser -u ec2-user -- $d/.venv/bin/python -I -c 'import sys,duckdb;print(sys.version.split()[0], duckdb.__version__)' 2>&1 | tail -1)"
done
sha256sum /w/batch13a1/ctp/validate_schema.py /w/batch13a1/ctp/validate.py 2>&1
git -C /w/batch13a1/ctp log -1 --format='%H %s' 2>&1 | cut -c1-100
command -v aws; aws --version 2>&1 | head -1
free -g | head -2; nproc; ls -la /home/ec2-user/NO_SHUTDOWN
df -h /data1 | tail -1
