#!/usr/bin/env bash
# probe_hosts.sh: for each non-GitHub host of the pool files, ask GET /api/v4/projects?per_page=1
# (GitLab API v4, documented). A JSON list answer means the host runs GitLab. Writes hosts.probe.tsv.
set -uo pipefail
out=hosts.probe.tsv; echo -e "host\thttp\tis_gitlab\tx_total\tprobed_at" > $out
while read -r h; do
  hdr=$(mktemp); body=$(timeout 25 curl -s -L --max-redirs 2 -D $hdr "https://$h/api/v4/projects?per_page=1" 2>/dev/null | head -c 2000)
  code=$(grep -i '^HTTP/' $hdr | tail -1 | awk '{print $2}'); tot=$(grep -i '^x-total:' $hdr | tail -1 | awk '{print $2}' | tr -d '\r')
  g=no; python3 -I -c 'import json,sys; d=json.loads(sys.argv[1]); assert isinstance(d,list) and (not d or "path_with_namespace" in d[0])' "$body" 2>/dev/null && g=yes
  echo -e "$h\t${code:-none}\t$g\t${tot:-}\t$(date -u +%FT%TZ)" >> $out; rm -f $hdr; sleep 1
done
