# P1-probe.sh (read-only): the state of census L7-20 and the big EC2 before L7-20b.
set -u
echo "== $(date -u +%FT%TZ) $(uptime)"
nproc; free -g | head -2
echo "MemAvailable $(awk '/MemAvailable/{printf "%.1f GiB", $2/1048576}' /proc/meminfo)"
df -BG /data / | cat; ls -ls --block-size=G /data/loop/ ; findmnt -lno TARGET,SOURCE,FSTYPE | grep -E '^/b' | cat
echo "== units"
systemctl list-units --no-legend --plain --all 'census*' 'cregit*' | awk '{print $1, $3, $4}'
systemctl list-timers --no-legend --all 'census*' 'cregit*' | cat
echo "== L7-20 unit"
systemctl cat census-L7-20.service | cat
cat /usr/local/bin/census-L7-20-run
systemctl show census-L7-20.service -p MainPID -p ActiveEnterTimestamp -p NeedDaemonReload | cat
pid=$(systemctl show census-L7-20.service -p MainPID --value); tr '\0' ' ' < /proc/$pid/cmdline; echo; readlink /proc/$pid/cwd
echo "== STOP files"; ls -la /bL7/ctp/STOP* /bL22/ctp/STOP* /b5L/ctp/STOP* 2>&1
echo "== L7-20 ctp"; git -C /bL7/ctp log --oneline -1; git -C /bL7/ctp status --short | head; ls -la /bL7/ctp | head -40
git -C /bL7/cregit-ec2 log --oneline -1; git -C /bL7/cregit-ec2 status --porcelain --untracked-files=no | wc -l
ls -la /bL7/cregit-ec2 /bL7/cregit-ec2/tokenizeByBlobId | head -50
du -sh --exclude=build /bL7/cregit-ec2 2>/dev/null; du -sh /bL7/cregit-ec2/tokenizeByBlobId/build
echo "== inputs"; ls -la /home/ec2-user/L7-20-input/; (cd /home/ec2-user/L7-20-input && sha256sum -c SHA256SUMS)
echo "== ledger events"; wc -l /bL7/ctp/ledger.jsonl; head -c 1500 /bL7/ctp/ledger.jsonl; echo; echo ...; tail -n 3 /bL7/ctp/ledger.jsonl | cut -c1-800
python3 - <<'P'
import json,collections
ev=collections.Counter(); keys=collections.Counter()
for l in open('/bL7/ctp/ledger.jsonl'):
    try: r=json.loads(l)
    except Exception: continue
    ev[r.get('event') or r.get('kind') or r.get('type') or '?']+=1
    keys[tuple(sorted(r.keys()))]+=1
print(ev); 
for k,v in keys.items(): print(v,k)
P
echo "== census-steps"; /usr/local/bin/census-steps --counts /bL7/ctp /home/ec2-user/L7-20-input/manifest.L7-20.tsv; /usr/local/bin/census-steps /bL7/ctp /home/ec2-user/L7-20-input/manifest.L7-20.tsv --highlight '' 2>&1 | head -30
head -40 /usr/local/bin/census-steps
echo "== log tail"; tail -n 15 /data/logs/L7-20.log | cut -c1-250
echo "== project_meta"; python3 -c "
import json;d=json.load(open('/home/ec2-user/L7-20-input/project_meta.L7-20.json'));print(type(d).__name__, len(d)); 
k=list(d)[:2] if isinstance(d,dict) else None; print(k); print(json.dumps(d[k[0]] if k else d[0])[:600])"
echo "== other"; ls /etc/cregit-census/; tail -1 /etc/cregit-census/L7-20.gate; ls /usr/local/bin/ | tr '\n' ' '; echo
ls -la /home/ec2-user/ | head -60
