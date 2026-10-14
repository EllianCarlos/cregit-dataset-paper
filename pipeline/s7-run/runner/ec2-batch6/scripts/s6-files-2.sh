set -euo pipefail
[ -e /usr/local/bin/census-spot-decide.orig-b3b5 ] || cp -p /usr/local/bin/census-spot-decide /usr/local/bin/census-spot-decide.orig-b3b5
cat > /usr/local/bin/census-fed-upload.new <<'EOF_census-fed-upload'
#!/usr/bin/env python3
"""census-fed-upload (census-fed-upload.timer, every minute): copy each finished project to S3.

Made from census-b5-upload (2026-10-09 ~20:10 UTC); only parts() differs. It covers every fed part
started on this spot instance (/etc/cregit-census/fed/started; each part's WL, PART, CTP, OUT, MP from
/etc/cregit-census/fed/<id>.env). A project is finished when its last final ledger
row ("project") says done or done-dirty and its .validated stamp exists. For each one not yet
uploaded it copies OUT/<name>/<name>-dataset.parquet, OUT/<name>/<name>.validated, OUT/<name>/<name>-persons.db (if it exists), ctp
state/<name>/*.json and state/<name>/logs/* (regular files) and a ledger.jsonl snapshot to
s3://BUCKET/<workload>/<part>/done/<name>/, lists the prefix back and compares every key and size,
then writes done/<name>/OK (time, instance, part, files, sizes, Parquet sha256) and a local marker
MP/uploaded/<name>. A restart leaves out exactly the projects that have OK.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

B = "s3://${RUNNER_BUCKET}"


def env(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def parts():
    fed = os.environ.get("FED_DIR", "/etc/cregit-census/fed")
    try:
        ids = Path(f"{fed}/started").read_text().split()
    except OSError:
        return []
    return [env(f"{fed}/{i}.env") for i in ids]


def finished(ctp):
    final = {}
    try:
        with (ctp / "ledger.jsonl").open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("step") == "project" and r.get("project"):
                    final[r["project"]] = r.get("state")
    except OSError:
        return []
    return [p for p, s in final.items() if s in ("done", "done-dirty")]


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def upload(name, e):
    ctp, out, mp = Path(e["CTP"]), Path(e["OUT"]), Path(e["MP"])
    dest = f"{B}/{e['WL']}/{e['PART']}/done"
    pq = out / name / f"{name}-dataset.parquet"
    stamp = out / name / f"{name}.validated"
    if not (pq.is_file() and stamp.is_file()):
        return f"{e['ID']} {name}: Parquet or stamp missing, later"
    stage = mp / "upload-stage"  # same filesystem as OUT, so os.link works
    stage.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}.", dir=stage))
    try:
        for f in (pq, stamp):
            os.link(f, tmp / f.name)
        persons = out / name / f"{name}-persons.db"  # 2026-10-11: also the persons DB
        if persons.is_file():
            os.link(persons, tmp / persons.name)
        st = ctp / "state" / name
        (tmp / "state" / "logs").mkdir(parents=True)
        for f in st.glob("*.json"):
            if f.is_file() and not f.is_symlink():
                shutil.copy2(f, tmp / "state" / f.name)
        for f in (st / "logs").glob("*"):
            if f.is_file() and not f.is_symlink():
                shutil.copy2(f, tmp / "state" / "logs" / f.name)
        shutil.copy2(ctp / "ledger.jsonl", tmp / "ledger.jsonl")
        local = {str(p.relative_to(tmp)): p.stat().st_size for p in tmp.rglob("*") if p.is_file()}
        subprocess.run(["aws", "s3", "cp", f"{tmp}/", f"{dest}/{name}/", "--recursive",
                        "--only-show-errors"], check=True)
        ls = subprocess.run(["aws", "s3", "ls", f"{dest}/{name}/", "--recursive"], check=True,
                            capture_output=True, text=True).stdout
        prefix = dest.split("/", 3)[3] + f"/{name}/"
        remote = {}
        for line in ls.splitlines():
            c = line.split(None, 3)
            if len(c) == 4 and c[3].startswith(prefix):
                remote[c[3][len(prefix):]] = int(c[2])
        bad = [k for k, v in local.items() if remote.get(k) != v]
        if bad:
            return f"{e['ID']} {name}: size check FAILED for {bad[:5]}, will retry"
        ok = tmp / "OK"
        instance = Path("/sys/devices/virtual/dmi/id/board_asset_tag").read_text().strip()
        ok.write_text(f"uploaded {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} from {instance} part {e['ID']}\n"
                      f"parquet_sha256 {sha256(pq)}\n"
                      + "".join(f"{v}\t{k}\n" for k, v in sorted(local.items())))
        subprocess.run(["aws", "s3", "cp", str(ok), f"{dest}/{name}/OK", "--only-show-errors"], check=True)
        (mp / "uploaded").mkdir(parents=True, exist_ok=True)
        (mp / "uploaded" / name).write_text(ok.read_text())
        return f"{e['ID']} {name}: uploaded {len(local)} files, sizes equal, OK written"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for e in parts():
        for name in finished(Path(e["CTP"])):
            if (Path(e["MP"]) / "uploaded" / name).exists():
                continue
            try:
                print(time.strftime("%FT%TZ", time.gmtime()), upload(name, e), flush=True)
            except (subprocess.CalledProcessError, OSError) as x:
                print(time.strftime("%FT%TZ", time.gmtime()), f"{e['ID']} {name}: upload error {x}, will retry", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
EOF_census-fed-upload
chmod 755 /usr/local/bin/census-fed-upload.new
mv -f /usr/local/bin/census-fed-upload.new /usr/local/bin/census-fed-upload
cat > /usr/local/bin/census-fed-live.new <<'EOF_census-fed-live'
#!/usr/bin/env bash
# Every 10 min (census-fed-live.timer, ec2-user; census-fed-trim runs before it as root): status of the
# fed parts of this spot instance to s3://BUCKET/feed/<half>/live/ (the combined view, read by the local
# watchdog and status_all.sh) and to each started part's s3://BUCKET/<workload>/<part>/live/:
#   progress.txt  first line "as of <ts>  census-fed on <iid> (spot <x>): <state> ( <id>=<unit state> ... )
#                 queue=<n> (<next>) feeder: <status>  b5=<active>/<parts>  batch3=<state>"; <state> is
#                 active (a fed part or its finalize runs), waiting (parts queued, the feeder waits for a
#                 slot, memory or the workload's cregit commit), paused (PAUSE exists), interrupted (spot
#                 notice), finalized (queue empty, every started part has its final DONE) or stopped.
#                 Then load, memory, the queue, the workloads' cregit commits, and per part: unit, free
#                 space, ctp progress and the step table.
#   steps.txt (per part), <id>.log.tail, ledger.jsonl, system.txt.
set -uo pipefail
. /usr/local/bin/census-fed-common
X=$(fed_half); IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
T=$(mktemp -d); trap 'rm -r "$T"' EXIT
IDS=$(fed_started | tr '\n' ' '); q=$(grep -c . $FED/queue 2>/dev/null || true)
st=""; any=no; fin=yes
for id in $IDS; do s=$(systemctl is-active census-fed@$id.service); st="$st $id=$s"
  case $s in active|activating|deactivating) any=yes ;; esac
  fed_active census-fed-finalize@$id.service && any=yes
  . $FED/$id.env; [ -e $MP/final-DONE ] || fin=no; done
if [ -e /run/census-spot-interrupted ]; then state=interrupted
elif [ $any = yes ]; then state=active
elif [ "$q" -gt 0 ]; then if [ -e $FED/PAUSE ]; then state=paused; else state=waiting; fi
elif [ $fin = yes ]; then state=finalized
else state=stopped; fi
b5a=0; b5n=0; if [ -f /etc/cregit-census/s5/batch.env ]; then for i in $(. /etc/cregit-census/s5/batch.env; echo $IDS); do b5n=$((b5n+1)); fed_active census-b5@$i.service && b5a=$((b5a+1)); done; fi
b3=none; if grep -qx b3 /etc/cregit-census/censuses 2>/dev/null; then b3=inactive
  for p in $(. /etc/cregit-census/batch.env; echo $PARTS); do fed_active census-b3@$p.service && b3=active; done; fi
# parts that are finished (unit inactive and final DONE) get one line and no per-part upload, so the
# pass stays short with many started parts (batches 6-20: up to ~75 per instance)
LIVE=""; for id in $IDS; do . $FED/$id.env
  if [ -e $MP/final-DONE ] && ! fed_active census-fed@$id.service && ! fed_active census-fed-finalize@$id.service; then continue; fi
  LIVE="$LIVE $id"
  /usr/local/bin/census-steps "$CTP" $IN/manifest.$id.run.tsv --highlight '' > "$T/steps.$id.txt" 2>&1; done
{ echo "as of $(date -u +%FT%TZ)  census-fed on $IID (spot $X): $state ($st )  queue=$q ($(head -1 $FED/queue 2>/dev/null | tr -d ' '))  feeder: $(cut -c22- /run/census-fed-feeder.status 2>/dev/null | cut -c1-120)  b5=$b5a/$b5n  batch3=$b3$([ -e /home/ec2-user/NO_SHUTDOWN ] && echo '  NO_SHUTDOWN')"
  echo "uptime: $(uptime)"
  echo "MemAvailable: $(awk '/MemAvailable/{printf "%.1f GiB", $2/1048576}' /proc/meminfo)   watcher: $(systemctl is-active census-fed-watch.service)   feeder timer: $(systemctl is-active census-fed-feeder.timer)   slots: $(cat $FED/slots 2>/dev/null || echo 5)"
  echo "queue: $(tr '\n' ',' < $FED/queue 2>/dev/null)   started: $IDS"
  [ -e $FED/PAUSE ] && echo "PAUSE: $(cat $FED/PAUSE)"
  for f in $FED/wl/*.env; do [ -f $f ] && echo "workload $(basename $f .env): $(grep -e CREGIT_COMMIT -e WANT_PQ $f | tr '\n' ' ')"; done
  echo "censuses: $(tr '\n' ' ' < /etc/cregit-census/censuses)  uploaded to done/ (fed): $(for id in $IDS; do . $FED/$id.env; ls $MP/uploaded 2>/dev/null; done | wc -l)"
  echo "finished parts (final DONE): $(for id in $IDS; do case " $LIVE " in *" $id "*) ;; *) echo -n "$id " ;; esac; done)"
  for id in $LIVE; do . $FED/$id.env
    echo; echo "=== part $id ($WL/$PART): census-fed@$id $(systemctl is-active census-fed@$id.service) ($(systemctl show census-fed@$id.service -p Result --value)), cregit $(git -C $CREGIT rev-parse --short HEAD), $MP free $(df -BG --output=avail $MP | tail -1 | tr -d ' '), image $(du -BG $IMG | cut -f1)$([ -e $CTP/STOP ] && echo '  STOP present')$([ -e $MP/final-DONE ] && echo '  final DONE')"
    (cd "$CTP" && CTP_CONFIG=$CFG .venv/bin/python ctp.py progress --manifest $IN/manifest.$id.run.tsv --last 5 2>&1)
    echo; cat "$T/steps.$id.txt"
  done
} > "$T/progress.txt"
{ date -u +%FT%TZ; uptime; cat /proc/pressure/io /proc/pressure/cpu 2>/dev/null; cat /proc/meminfo; df -h /data /data[0-9]* /w/* / 2>/dev/null; du -h /data*/loop/*.img 2>/dev/null; } > "$T/system.txt"
mkdir -p $T/c; cp $T/progress.txt $T/system.txt $T/c/; tail -n 200 /data/logs/fed-feeder.log > $T/c/fed-feeder.log.tail 2>/dev/null
aws s3 cp $T/c/ "$BUCKET/feed/$X/live/" --recursive --only-show-errors
for id in $LIVE; do . $FED/$id.env; mkdir -p $T/p/$id
  cp $T/progress.txt $T/system.txt $T/p/$id/; cp $T/steps.$id.txt $T/p/$id/steps.txt
  tail -n 300 "$LOG" > $T/p/$id/$id.log.tail 2>/dev/null
  [ -f "$CTP/ledger.jsonl" ] && cp "$CTP/ledger.jsonl" $T/p/$id/ledger.jsonl
  aws s3 cp $T/p/$id/ "$BUCKET/$WL/$PART/live/" --recursive --only-show-errors
done
EOF_census-fed-live
chmod 755 /usr/local/bin/census-fed-live.new
mv -f /usr/local/bin/census-fed-live.new /usr/local/bin/census-fed-live
cat > /usr/local/bin/census-fed-trim.new <<'EOF_census-fed-trim'
#!/usr/bin/env bash
# census-fed-trim (root, before every census-fed-live): fstrim each started fed part's loop XFS /w/<id>,
# so blocks freed inside (cleaned-up clones) are punched out of the sparse image.
for id in $(cat /etc/cregit-census/fed/started 2>/dev/null); do [ -e /w/$id/final-DONE ] && continue; mountpoint -q /w/$id && fstrim /w/$id >/dev/null 2>&1; done
exit 0
EOF_census-fed-trim
chmod 755 /usr/local/bin/census-fed-trim.new
mv -f /usr/local/bin/census-fed-trim.new /usr/local/bin/census-fed-trim
cat > /usr/local/bin/census-fed-watch.new <<'EOF_census-fed-watch'
#!/usr/bin/env bash
# census-fed-watch (census-fed-watch.service, root): poll IMDSv2 spot/instance-action every 5 s, as
# census-b5-watch does for the census-b5 parts. On a notice: write /run/census-spot-interrupted (the
# feeder then starts nothing), touch STOP in every started fed part's ctp clone (no new project starts),
# write INTERRUPTED (time, notice, running projects) and the part's ledger to each part's
# s3://BUCKET/<workload>/<part>/live/ and to feed/<half>/live/, and run census-fed-upload once. EC2
# terminates the instance about 2 min later; restart_spot.sh relaunches the unfinished work, with the
# queued and unfinished fed parts.
# Test mode: if /run/census-fed-fake-spot-notice exists, its content is the notice; STOP then goes to
# /run/census-fed-STOP.test.<id>, the S3 names get a .test suffix and /run/census-spot-interrupted is
# not written, so nothing stops. The fake file is removed after it is handled and watching goes on.
set -uo pipefail
. /usr/local/bin/census-fed-common
FAKE=/run/census-fed-fake-spot-notice
IMDS=http://169.254.169.254/latest
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
handle() {  # $1 notice, $2 suffix ("" or .test)
  local notice=$1 sfx=$2 T id X; T=$(mktemp -d); X=$(fed_half)
  for id in $(fed_started); do . $FED/$id.env
    if [ -z "$sfx" ]; then stop=$CTP/STOP; else stop=/run/census-fed-STOP.test.$id; fi
    touch "$stop"; chown ec2-user: "$stop"
  done
  { echo "spot interruption notice seen $(date -u +%FT%TZ) on $IID (spot $X)${sfx:+  TEST, census not stopped}"
    echo "notice: $notice"; echo "queue: $(tr '\n' ',' < $FED/queue)"; echo "started: $(fed_started | tr '\n' ' ')"; } > $T/INTERRUPTED$sfx
  aws s3 cp $T/INTERRUPTED$sfx "$BUCKET/feed/$X/live/INTERRUPTED$sfx" --only-show-errors
  for id in $(fed_started); do . $FED/$id.env; mkdir -p $T/$id
    { cat $T/INTERRUPTED$sfx
      echo "part $id STOP: $([ -z "$sfx" ] && echo "$CTP/STOP" || echo /run/census-fed-STOP.test.$id)"
      /usr/local/bin/census-steps "$CTP" $IN/manifest.$id.run.tsv --highlight '' 2>&1
      echo "uploaded to done/ so far: $(ls $MP/uploaded 2>/dev/null | wc -l)"
    } > "$T/$id/INTERRUPTED$sfx"
    [ -f "$CTP/ledger.jsonl" ] && cp "$CTP/ledger.jsonl" "$T/$id/ledger$sfx.jsonl"
    aws s3 cp "$T/$id/" "$BUCKET/$WL/$PART/live/" --recursive --only-show-errors
  done
  echo "$(date -u +%FT%TZ) handled notice${sfx:+ (test)}: $notice"
  sudo -u ec2-user /usr/local/bin/census-fed-upload
  rm -r "$T"
}
echo "$(date -u +%FT%TZ) watching $IMDS/meta-data/spot/instance-action every 5 s (fed parts)"
while :; do
  if [ -e $FAKE ]; then handle "$(cat $FAKE)" .test; rm -f $FAKE; sleep 5; continue; fi
  tok=$(curl -s -m 2 -X PUT "$IMDS/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
  if [ -n "$tok" ]; then
    code=$(curl -s -m 2 -o /run/census-fed-instance-action -w '%{http_code}' -H "X-aws-ec2-metadata-token: $tok" "$IMDS/meta-data/spot/instance-action")
    if [ "$code" = 200 ]; then echo "$(date -u +%FT%TZ) $(cat /run/census-fed-instance-action)" > /run/census-spot-interrupted
      handle "$(cat /run/census-fed-instance-action)" ""; echo "real notice handled; idle until termination"; exec sleep infinity; fi
  fi
  sleep 5
done
EOF_census-fed-watch
chmod 755 /usr/local/bin/census-fed-watch.new
mv -f /usr/local/bin/census-fed-watch.new /usr/local/bin/census-fed-watch
cat > /usr/local/bin/census-spot-decide.new <<'EOF_census-spot-decide'
#!/usr/bin/env bash
# census-spot-decide (2026-10-09): exit 0 when EVERY census on this spot instance has finalized, so
# the instance may terminate; otherwise print why not and exit 1. Called by census-b3-finalize and
# census-b5-finalize just before they would shut down (shutdown behavior terminate); each writes its
# own DONE first, so only the last census to finalize terminates the instance.
# The censuses of this instance are the words in /etc/cregit-census/censuses (default "b3", the
# batch 3 rule before 2026-10-09):
#   b3: no census-b3@<part> (PARTS of /etc/cregit-census/batch.env) is active, and
#       s3://BUCKET/batch3/<a|b>/final/<instance-id>/DONE exists (census-b3-finalize, after its check);
#   b5: no census-b5@<id> (IDS of /etc/cregit-census/s5/batch.env) is active, and for every part
#       s3://BUCKET/<workload>/<part>/final/<instance-id>/DONE exists (census-b5-finalize).
#   fed (2026-10-09 ~20:10 UTC, the fed parts of batch 6 and later): the queue
#       /etc/cregit-census/fed/queue is empty, no census-fed@<id> of the
#       started list /etc/cregit-census/fed/started is active, and for every started part (a part whose
#       finalize still copies has no DONE yet)
#       s3://BUCKET/<workload>/<part>/final/<instance-id>/DONE exists (census-fed-finalize). The feeder
#       adds a part to the started list before it removes it from the queue, so a part being started
#       is always seen.
# Test overrides: CENSUSES (the list), IID, BUCKET_DONE (prefix used for the DONE lookups instead of
# s3://BUCKET; e.g. a dry-run prefix), UNITS_b3 / UNITS_b5 / UNITS_fed (space-separated units; "" = none),
# FED_DIR (instead of /etc/cregit-census/fed: its queue, started and <id>.env).
set -uo pipefail
export AWS_PAGER=""
B=${BUCKET_DONE:-s3://${RUNNER_BUCKET}}
IID=${IID:-$(cat /sys/devices/virtual/dmi/id/board_asset_tag)}
CENSUSES=${CENSUSES-$(cat /etc/cregit-census/censuses 2>/dev/null || echo b3)}
[ -n "$(echo $CENSUSES)" ] || CENSUSES=b3
ok=""
for c in $CENSUSES; do
  case $c in
    b3) . /etc/cregit-census/batch.env
        units=${UNITS_b3-$(for p in $PARTS; do echo census-b3@$p.service; done)}
        urls="$B/batch3/$BATCH/final/$IID/DONE" ;;
    b5) . /etc/cregit-census/s5/batch.env
        units=${UNITS_b5-$(for i in $IDS; do echo census-b5@$i.service; done)}
        urls=$(for i in $IDS; do . /etc/cregit-census/s5/$i.env; echo "$B/$WL/$PART/final/$IID/DONE"; done) ;;
    fed) F=${FED_DIR:-/etc/cregit-census/fed}
        nq=$(grep -c . $F/queue 2>/dev/null || true)
        [ "${nq:-0}" = 0 ] || { echo "census fed not finalized: $nq parts queued ($(head -1 $F/queue))"; exit 1; }
        ids=$(cat $F/started 2>/dev/null)
        units=${UNITS_fed-$(for i in $ids; do echo census-fed@$i.service; done)}
        urls=$(for i in $ids; do . $F/$i.env; echo "$B/$WL/$PART/final/$IID/DONE"; done) ;;
    *) echo "unknown census '$c' in /etc/cregit-census/censuses"; exit 2 ;;
  esac
  for u in $units; do s=$(systemctl is-active "$u")
    case $s in active|activating|reloading|deactivating) echo "census $c not finalized: $u is $s"; exit 1 ;; esac; done
  for url in $urls; do aws s3 ls "$url" >/dev/null 2>&1 || { echo "census $c not finalized: $url is missing"; exit 1; }; done
  ok="$ok $c($(echo $urls | wc -w) DONE)"
done
echo "every census on this instance finalized:$ok (units not active, DONE in S3)"
EOF_census-spot-decide
chmod 755 /usr/local/bin/census-spot-decide.new
mv -f /usr/local/bin/census-spot-decide.new /usr/local/bin/census-spot-decide
uchanged=0
cat > /etc/systemd/system/census-fed@.service.new <<'EOF_census-fed@.service'
[Unit]
Description=cregit census fed spot part %i (ctp census, own loop XFS /w/%i)
Wants=network-online.target
After=network-online.target nix-daemon.service
RequiresMountsFor=/w/%i
OnSuccess=census-fed-finalize@%i.service
OnFailure=census-fed-finalize@%i.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/w/%i/ctp
ExecStart=/usr/local/bin/census-fed-run %i
StandardOutput=append:/data/logs/fed-%i.log
StandardError=append:/data/logs/fed-%i.log
Restart=no
# an OOM kill of one project must not stop the whole census (systemd default is stop)
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStopSec=300
EOF_census-fed@.service
chmod 644 /etc/systemd/system/census-fed@.service.new
if cmp -s /etc/systemd/system/census-fed@.service.new /etc/systemd/system/census-fed@.service; then rm -f /etc/systemd/system/census-fed@.service.new; else mv -f /etc/systemd/system/census-fed@.service.new /etc/systemd/system/census-fed@.service; uchanged=1; fi
cat > /etc/systemd/system/census-fed-finalize@.service.new <<'EOF_census-fed-finalize@.service'
[Unit]
Description=cregit census fed spot part %i: copy results to S3, write DONE, feed the next part, terminate if every census on the instance finalized

[Service]
Type=oneshot
ExecStart=/usr/local/bin/census-fed-finalize %i
TimeoutStartSec=infinity
EOF_census-fed-finalize@.service
chmod 644 /etc/systemd/system/census-fed-finalize@.service.new
if cmp -s /etc/systemd/system/census-fed-finalize@.service.new /etc/systemd/system/census-fed-finalize@.service; then rm -f /etc/systemd/system/census-fed-finalize@.service.new; else mv -f /etc/systemd/system/census-fed-finalize@.service.new /etc/systemd/system/census-fed-finalize@.service; uchanged=1; fi
cat > /etc/systemd/system/census-fed-feeder.service.new <<'EOF_census-fed-feeder.service'
[Unit]
Description=cregit census fed spot parts: start the next queued part when a slot is free

[Service]
Type=oneshot
ExecStart=/usr/local/bin/census-fed-feeder
TimeoutStartSec=3600
EOF_census-fed-feeder.service
chmod 644 /etc/systemd/system/census-fed-feeder.service.new
if cmp -s /etc/systemd/system/census-fed-feeder.service.new /etc/systemd/system/census-fed-feeder.service; then rm -f /etc/systemd/system/census-fed-feeder.service.new; else mv -f /etc/systemd/system/census-fed-feeder.service.new /etc/systemd/system/census-fed-feeder.service; uchanged=1; fi
cat > /etc/systemd/system/census-fed-feeder.timer.new <<'EOF_census-fed-feeder.timer'
[Unit]
Description=cregit census fed spot parts: feeder every minute

[Timer]
OnActiveSec=1min
OnUnitActiveSec=1min
AccuracySec=10s
EOF_census-fed-feeder.timer
chmod 644 /etc/systemd/system/census-fed-feeder.timer.new
if cmp -s /etc/systemd/system/census-fed-feeder.timer.new /etc/systemd/system/census-fed-feeder.timer; then rm -f /etc/systemd/system/census-fed-feeder.timer.new; else mv -f /etc/systemd/system/census-fed-feeder.timer.new /etc/systemd/system/census-fed-feeder.timer; uchanged=1; fi
cat > /etc/systemd/system/census-fed-upload.service.new <<'EOF_census-fed-upload.service'
[Unit]
Description=cregit census fed spot parts: copy finished projects to S3 <workload>/<part>/done/

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/census-fed-upload
TimeoutStartSec=3600
EOF_census-fed-upload.service
chmod 644 /etc/systemd/system/census-fed-upload.service.new
if cmp -s /etc/systemd/system/census-fed-upload.service.new /etc/systemd/system/census-fed-upload.service; then rm -f /etc/systemd/system/census-fed-upload.service.new; else mv -f /etc/systemd/system/census-fed-upload.service.new /etc/systemd/system/census-fed-upload.service; uchanged=1; fi
cat > /etc/systemd/system/census-fed-upload.timer.new <<'EOF_census-fed-upload.timer'
[Unit]
Description=cregit census fed spot parts: copy finished projects to S3 every minute

[Timer]
OnActiveSec=1min
OnUnitActiveSec=1min
AccuracySec=10s
EOF_census-fed-upload.timer
chmod 644 /etc/systemd/system/census-fed-upload.timer.new
if cmp -s /etc/systemd/system/census-fed-upload.timer.new /etc/systemd/system/census-fed-upload.timer; then rm -f /etc/systemd/system/census-fed-upload.timer.new; else mv -f /etc/systemd/system/census-fed-upload.timer.new /etc/systemd/system/census-fed-upload.timer; uchanged=1; fi
cat > /etc/systemd/system/census-fed-live.service.new <<'EOF_census-fed-live.service'
[Unit]
Description=cregit census fed spot parts: live status to S3

[Service]
Type=oneshot
User=ec2-user
# fstrim of the loop filesystems needs root ("+"): it hands freed blocks back to the host disk
ExecStartPre=+/usr/local/bin/census-fed-trim
ExecStart=/usr/local/bin/census-fed-live
TimeoutStartSec=600
EOF_census-fed-live.service
chmod 644 /etc/systemd/system/census-fed-live.service.new
if cmp -s /etc/systemd/system/census-fed-live.service.new /etc/systemd/system/census-fed-live.service; then rm -f /etc/systemd/system/census-fed-live.service.new; else mv -f /etc/systemd/system/census-fed-live.service.new /etc/systemd/system/census-fed-live.service; uchanged=1; fi
cat > /etc/systemd/system/census-fed-live.timer.new <<'EOF_census-fed-live.timer'
[Unit]
Description=cregit census fed spot parts: live status to S3 every 10 min

[Timer]
OnActiveSec=1min
OnUnitActiveSec=10min
AccuracySec=30s
EOF_census-fed-live.timer
chmod 644 /etc/systemd/system/census-fed-live.timer.new
if cmp -s /etc/systemd/system/census-fed-live.timer.new /etc/systemd/system/census-fed-live.timer; then rm -f /etc/systemd/system/census-fed-live.timer.new; else mv -f /etc/systemd/system/census-fed-live.timer.new /etc/systemd/system/census-fed-live.timer; uchanged=1; fi
cat > /etc/systemd/system/census-fed-watch.service.new <<'EOF_census-fed-watch.service'
[Unit]
Description=cregit census fed spot parts: watch for a spot interruption notice (IMDSv2)
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/census-fed-watch
Restart=always
RestartSec=5
EOF_census-fed-watch.service
chmod 644 /etc/systemd/system/census-fed-watch.service.new
if cmp -s /etc/systemd/system/census-fed-watch.service.new /etc/systemd/system/census-fed-watch.service; then rm -f /etc/systemd/system/census-fed-watch.service.new; else mv -f /etc/systemd/system/census-fed-watch.service.new /etc/systemd/system/census-fed-watch.service; uchanged=1; fi
if [ $uchanged = 0 ]; then echo "unit files unchanged: no daemon-reload"; else
for u in $(systemctl list-units --no-legend --plain --all "census*" | awk "{print \$1}"); do [ "$(systemctl show $u -p NeedDaemonReload --value)" = no ] || { echo "$u: NeedDaemonReload=yes; no daemon-reload"; exit 1; }; done
before=$(for u in $(systemctl list-units --no-legend --plain "census-b*@*.service" | awk "{print \$1}"); do echo "$u $(systemctl show $u -p MainPID -p ActiveEnterTimestamp --value | tr "\n" " ")"; done)
systemctl daemon-reload
after=$(for u in $(systemctl list-units --no-legend --plain "census-b*@*.service" | awk "{print \$1}"); do echo "$u $(systemctl show $u -p MainPID -p ActiveEnterTimestamp --value | tr "\n" " ")"; done)
[ "$before" = "$after" ] && echo "running census units unchanged by daemon-reload ($(echo "$before" | grep -c .) units)" || { echo "CHANGED:"; diff <(echo "$before") <(echo "$after"); }
fi
echo "s6 files 2 installed: $(sha256sum /usr/local/bin/census-spot-decide /usr/local/bin/census-fed-feeder /usr/local/bin/census-fed-finalize | cut -c1-12 | tr "\n" " ")"
