#!/bin/bash
# machine B: reset pass 2 after the DuckDB segfault (kit message: remove status/pseudo.DONE, final53, registries; new salt)
set -u
systemctl is-active --quiet ta-run && { systemctl stop ta-run; sleep 2; }
ts=$(date -u +%Y%m%dT%H%M%SZ)
cd /data/ta || exit 1
[ -f status/pseudo.DONE ] && mv status/pseudo.DONE status/pseudo.DONE.old.$ts
[ -d final53 ] && mv final53 final53.old.$ts
[ -d private/registries ] && mv private/registries private/registries.old.$ts
[ -d private/write-work ] && mv private/write-work private/write-work.old.$ts
ls status/ | tr '\n' ' '; echo; ls -d final53* private/registries* private/write-work* 2>/dev/null | tr '\n' ' '; echo
echo "ta-run: $(systemctl is-active ta-run)"; free -g | awk '/Mem:/{print "mem total "$2" GiB"}'
