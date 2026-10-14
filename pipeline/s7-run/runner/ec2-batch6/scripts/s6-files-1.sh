set -euo pipefail
cat > /usr/local/bin/census-fed-part-init.new <<'EOF_census-fed-part-init'
#!/usr/bin/env bash
# census-fed-part-init WORKLOAD PART (root; called by census-fed-feeder just before the part starts):
# the fed part <id> = WORKLOAD+PART (e.g. batch6a1) of this spot instance gets, as the census-b5 parts:
#   - its own sparse XFS image <host>/loop/<id>.img, loop-mounted at /w/<id> (own superblock, so its own
#     rename lock; fstab line with nofail). Host: a: the mounted /dataK with the most free space;
#     b: the RAID0 /data. Size min(1200G, 90% of the host's free space / (1 + images of running parts
#     on it)); ctp --disk-floor-gb min(300, size/4);
#   - its own ctp clone /w/<id>/ctp (ca113e3 from /data/input/ctp.bundle, Python 3.12 venv);
#   - its own cregit copy /w/<id>/cregit-ec2 of the checked /data/cregit-ec2 (95cdc88), with an empty
#     tokenizeByBlobId/build, checked out at the workload's CREGIT_COMMIT (census-fed-workload; fetched
#     from its git bundle); the path and the commit are fixed here, before the census starts (blobExec
#     stores the path);
#   - its config /etc/cregit-census/fed/<id>.cfg, env <id>.env and output /w/<id>/census-2026-10-<wl>.
# Idempotent: an existing env keeps its image, size and floor; existing mounts, clones, copies are kept.
set -euo pipefail
. /usr/local/bin/census-fed-common
wl=${1:?workload}; part=${2:?part}; id=$wl$part; X=$(fed_half)
w=$(awk -F'\t' -v q=$part '!/^#/ && $3==q {print $4}' $FI/$wl/parts.$wl.tsv); [ -n "$w" ] || { echo "$id not in parts.$wl.tsv" >&2; exit 2; }
[ -d /data/cregit-ec2 ] || { echo "no /data/cregit-ec2" >&2; exit 2; }
if [ -f $FED/$id.env ]; then . $FED/$id.env; h=$HOST; img=$IMG; sz=$SIZE_G; fl=$FLOOR
else
  if [ $X = a ]; then h=$(for d in /data[0-9]*; do mountpoint -q $d && echo "$(df -BG --output=avail $d | tail -1 | tr -dc 0-9) $d"; done | sort -rn | head -1 | cut -d' ' -f2)
  else h=$(readlink -f /data); fi
  [ -n "$h" ] || { echo "no host filesystem" >&2; exit 2; }
  h=$(readlink -f $h)
  # images on this host whose part still runs (a finished part's image keeps only its small output)
  act=0; for m in $(findmnt -rn -o TARGET | grep '^/w/'); do src=$(losetup -n -O BACK-FILE "$(findmnt -no SOURCE $m)" 2>/dev/null || true)
    i=${m#/w/}; fed_active census-fed@$i.service || fed_active census-b5@$i.service || fed_active census-b3@$i.service || continue
    case $src in $h/*) act=$((act+1)) ;; esac; done
  av=$(df -BG --output=avail $h | tail -1 | tr -dc 0-9); sz=$(( av * 9 / 10 / (act + 1) )); [ $sz -gt 1200 ] && sz=1200
  [ $sz -ge 200 ] || { echo "only ${sz}G for an image on $h: not enough space" >&2; exit 3; }
  fl=$(( sz / 4 )); [ $fl -gt 300 ] && fl=300; img=$h/loop/$id.img
fi
mp=/w/$id
mkdir -p $h/loop $mp
[ -e $img ] || { truncate -s ${sz}G $img; mkfs.xfs -q -L ${id:0:12} $img; }
grep -q "^$img " /etc/fstab || echo "$img $mp xfs loop,noatime,discard,nofail,x-systemd.requires-mounts-for=$h 0 0" >> /etc/fstab
mountpoint -q $mp || mount $mp
chown ec2-user: $mp
C=$mp/ctp; D=$mp/cregit-ec2; O=$mp/census-2026-10-$wl
sudo -u ec2-user bash -c "set -e; [ -d $C ] || git clone -q /data/input/ctp.bundle $C -b feat/e2e-runner; cd $C; [ \"\$(git rev-parse --short HEAD)\" = ca113e3 ]; [ -x .venv/bin/python ] || { python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; }; mkdir -p $O $mp/uploaded"
if [ ! -e $D ]; then
  # copy into a temp dir, then mv: a failed copy leaves no partial $D (a retry would skip it). The
  # tokenizer temp dir is left out as a whole, so writes in it during the copy cannot fail tar
  # (2026-10-10 07:41 UTC: "file changed as we read it").
  T=$mp/.cregit-copy; rm -rf $T; mkdir -p $T
  # 2026-10-12: blameRepo/build too (formatBlame.pl temp files of census-b3@a2, which runs in the
  # template on spot a: "file changed as we read it", feeder PAUSE at 00:58 UTC).
  tar -C /data/ -cf - --exclude='cregit-ec2/tokenizeByBlobId/build' --exclude='cregit-ec2/blameRepo/build' cregit-ec2 | tar -C $T -xpf -
  mv $T/cregit-ec2 $D; rmdir $T
  mkdir -p $D/tokenizeByBlobId/build $D/blameRepo/build; chown ec2-user: $D $D/tokenizeByBlobId/build $D/blameRepo/build
fi
# the workload's cregit commit (census-fed-workload): check the copy out at it before the census starts
WLE=$FED/wl/$wl.env; [ -f $WLE ] || { echo "no $WLE: run census-fed-workload $wl first" >&2; exit 2; }
. $WLE; [ "$CREGIT_COMMIT" != pending ] || { echo "$wl: cregit commit pending" >&2; exit 4; }
if [ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" != "$CREGIT_COMMIT" ]; then
  [ -n "$CREGIT_BUNDLE" ] || { echo "$D is at $(sudo -u ec2-user git -C $D rev-parse --short HEAD), $wl wants $CREGIT_COMMIT and has no bundle" >&2; exit 2; }
  bf=/data/input/$(basename "$CREGIT_BUNDLE")
  if [ ! -f $bf ] || [ "$(sha256sum $bf | cut -d' ' -f1)" != "$CREGIT_BUNDLE_SHA256" ]; then
    aws s3 cp "$CREGIT_BUNDLE" $bf.tmp --only-show-errors && mv -f $bf.tmp $bf; fi
  [ "$(sha256sum $bf | cut -d' ' -f1)" = "$CREGIT_BUNDLE_SHA256" ] || { echo "bundle $bf sha256 differs from $CREGIT_BUNDLE_SHA256" >&2; exit 2; }
  chmod 644 $bf
  [ -z "$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no)" ] || { echo "$D is dirty: no checkout" >&2; exit 2; }
  sudo -u ec2-user bash -c "set -e; cd $D; git bundle verify -q $bf >/dev/null 2>&1; git fetch -q $bf '+refs/heads/*:refs/remotes/fed-bundle/*'; git checkout -q --detach $CREGIT_COMMIT"
fi
[ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" = "$CREGIT_COMMIT" ] || { echo "$D is not at $CREGIT_COMMIT" >&2; exit 2; }
[ -z "$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no)" ] || { echo "$D is dirty after the checkout" >&2; exit 2; }
printf '# ctp config (CTP_CONFIG) for fed census part %s (%s, part %s) on spot half %s: cregit 95cdc88,\n# own copy %s, output on loop XFS %s (image %s).\n[paths]\ncregit_dir = %s\noutput_dir = %s\n' \
  $id $wl $part $X $D $mp $img $D $O > $FED/$id.cfg
[ -f $FED/$id.env ] || printf 'ID=%s\nWL=%s\nPART=%s\nHALF=%s\nWORKERS=%s\nHOST=%s\nIMG=%s\nSIZE_G=%s\nFLOOR=%s\nMP=%s\nCTP=%s\nCREGIT=%s\nOUT=%s\nCFG=%s\nLOG=%s\nIN=%s\nCREGIT_COMMIT=%s\n' \
  $id $wl $part $X $w $h $img $sz $fl $mp $C $D $O $FED/$id.cfg /data/logs/fed-$id.log $FI/$wl $CREGIT_COMMIT > $FED/$id.env
chmod 644 $FED/$id.env $FED/$id.cfg
echo "$id: $(findmnt -no SOURCE $mp) $img ${sz}G floor ${fl}G fsid=$(stat -f -c %i $mp) | ctp $(sudo -u ec2-user git -C $C rev-parse --short HEAD) | cregit $(sudo -u ec2-user git -C $D rev-parse --short HEAD) dirty=$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no | wc -l) build=$(ls -A $D/tokenizeByBlobId/build | wc -l) | $w workers"
EOF_census-fed-part-init
chmod 755 /usr/local/bin/census-fed-part-init.new
mv -f /usr/local/bin/census-fed-part-init.new /usr/local/bin/census-fed-part-init
cat > /usr/local/bin/census-fed-check.new <<'EOF_census-fed-check'
#!/usr/bin/env bash
# census-fed-check ID (root; census-fed-feeder runs it on every new fed part before its start): the
# identity gate of the part's own new cregit copy /w/<id>/cregit-ec2, as census-b5-check:
# libsrcml.so.1.1.0 sha256 through the copy's own devenv shell, the libexpat Parquet sha256 of a census
# with a scratch ctp clone /w/<id>/ctp-check and scratch output /w/<id>/libexpat-check/out (flags of the
# batch 2 check), and the blobExec jar sha256 against /data/cregit-ec2. All must equal the reference
# values of the workload (WANT_SRCML, WANT_PQ in /etc/cregit-census/fed/wl/<workload>.env), and the copy
# must be at the workload's CREGIT_COMMIT.
# Result: /etc/cregit-census/fed/<id>.check (last line "CHECK OK <time>" or "CHECK FAILED: ..."); exit 0 only if OK.
set -uo pipefail
. /usr/local/bin/census-fed-common
id=${1:?id}; . $FED/$id.env
# the expected values of the part's workload (census-fed-workload): they change with its cregit commit
. $FED/wl/$WL.env
[ "$(sudo -u ec2-user git -C $CREGIT rev-parse HEAD)" = "$CREGIT_COMMIT" ] || { echo "CHECK FAILED: $CREGIT is not at $CREGIT_COMMIT" | tee $FED/$id.check; exit 1; }
R=$FED/$id.check; echo "check of $CREGIT started $(date -u +%FT%TZ)" > $R; chmod 644 $R
fail() { echo "CHECK FAILED: $*" | tee -a $R; exit 1; }
printf '# libexpat check on the cregit copy %s (scratch output).\n[paths]\ncregit_dir = %s\noutput_dir = %s\n' $CREGIT $CREGIT $MP/libexpat-check/out > $FED/$id.check.cfg
chmod 644 $FED/$id.check.cfg
cat > /home/ec2-user/srcml-sha-fed-$id.sh <<U
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cd $CREGIT
devenv shell -- bash -c 'sha256sum "\$SRCML_PREFIX/lib/libsrcml.so.1.1.0"'
U
cat > /home/ec2-user/check-fed-$id.sh <<U
set -uo pipefail
C=$MP/ctp-check
[ -d \$C ] && mv \$C \$C.old.\$(date +%s)  # a fresh scratch clone: no ledger of an earlier check
[ -d \$C ] || git clone -q /data/input/ctp.bundle \$C -b feat/e2e-runner
cd \$C; [ "\$(git rev-parse --short HEAD)" = ca113e3 ] || { echo "wrong ctp HEAD"; exit 1; }
[ -x .venv/bin/python ] || { python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; }
export CTP_CONFIG=$FED/$id.check.cfg
[ -d $MP/libexpat-check/out ] && mv $MP/libexpat-check/out $MP/libexpat-check/out.old.\$(date +%s)
mkdir -p $MP/libexpat-check/out
.venv/bin/python ctp.py census --manifest /data/input/manifest.libexpat.tsv --project-meta /data/input/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10 > /data/logs/fed-check-$id.log 2>&1
echo "census rc=\$?"
U
mkdir -p /data/logs; chown ec2-user: /home/ec2-user/srcml-sha-fed-$id.sh /home/ec2-user/check-fed-$id.sh /data/logs
got_s=$(sudo -u ec2-user -i bash /home/ec2-user/srcml-sha-fed-$id.sh 2>/dev/null | grep -o '^[0-9a-f]\{64\}' | tail -1)
echo "libsrcml.so.1.1.0 sha256 $got_s (copy $CREGIT)" | tee -a $R
[ "$got_s" = "$WANT_SRCML" ] || fail "libsrcml sha256 differs"
t0=$(date +%s); sudo -u ec2-user -i bash /home/ec2-user/check-fed-$id.sh
got=$(sha256sum $MP/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet 2>/dev/null | cut -d' ' -f1)
echo "libexpat Parquet sha256 $got ($(( $(date +%s) - t0 )) s; cregit_dir $(grep -o '"cregit_dir": "[^"]*"' $MP/ctp-check/runs.log 2>/dev/null | tail -1))" | tee -a $R
[ "$got" = "$WANT_PQ" ] || fail "libexpat Parquet sha256 differs from $WANT_PQ"
jar() { find $1 -name '*.jar' -path '*blobExec*' -newer $1/README.md 2>/dev/null | head -1 | xargs -r sha256sum | cut -c1-16; }
ref=$(jar /data/cregit-ec2); [ -n "$ref" ] && [ "$(jar $CREGIT)" = "$ref" ] || fail "blobExec jar of $CREGIT ($(jar $CREGIT)) differs from /data/cregit-ec2 ($ref)"
echo "blobExec jar sha256 $ref in /data/cregit-ec2 and $CREGIT" | tee -a $R
echo "CHECK OK $(date -u +%FT%TZ) cregit $CREGIT_COMMIT libexpat $WANT_PQ" | tee -a $R
EOF_census-fed-check
chmod 755 /usr/local/bin/census-fed-check.new
mv -f /usr/local/bin/census-fed-check.new /usr/local/bin/census-fed-check
cat > /usr/local/bin/census-fed-feeder.new <<'EOF_census-fed-feeder'
#!/usr/bin/env bash
# census-fed-feeder [--dry-run] (root; census-fed-feeder.timer every minute, and census-fed-finalize
# after each fed part). While fewer than SLOTS parts run on this instance (census-b5@<id> of
# /etc/cregit-census/s5/batch.env plus census-fed@<id> of the started list; SLOTS from
# /etc/cregit-census/fed/slots, default 5) and the queue is not empty, it starts the next queued part:
#   0. the workload's cregit commit must be set (census-fed-workload; "pending" holds its parts);
#   1. census-fed-part-init (own loop XFS image, ctp clone, cregit copy whose path and commit are fixed
#      now, cfg, env);
#   2. the run manifest = the part manifest minus every project with done/OK (u order kept); a part
#      with nothing left is dropped from the queue;
#   3. census-fed-check, the libexpat identity gate on the part's new cregit copy;
#   4. the id is appended to the started list, then removed from the queue, then census-fed@<id> starts
#      (census-spot-decide sees either a queued part or a started part without its DONE: no termination).
# It holds (starts nothing) after a spot notice (/run/census-spot-interrupted), while
# /etc/cregit-census/fed/PAUSE exists, or while MemAvailable < MINMEM_GB (default 64). A failed
# part-init or check writes PAUSE with the reason and leaves the part at the head of the queue.
# Status: /run/census-fed-feeder.status; log: /data/logs/fed-feeder.log.
# --dry-run: print what it would start; changes nothing.
# Test overrides: FED_DIR, FED_INPUT (census-fed-common), B5_ENV (census-b5 batch.env; "" = none),
# FEED_UNIT (printf pattern of the part unit, default census-fed@%s.service), FEED_INIT, FEED_CHECK
# (commands run as "$FEED_INIT wl part" and "$FEED_CHECK id"), FEED_START (default "systemctl start"),
# FEED_RUNMAN (0 = skip step 2 and its S3 listing), MINMEM_GB.
set -uo pipefail
. /usr/local/bin/census-fed-common
B5_ENV=${B5_ENV-/etc/cregit-census/s5/batch.env}
UNIT=${FEED_UNIT:-census-fed@%s.service}
INIT=${FEED_INIT:-/usr/local/bin/census-fed-part-init}; CHECK=${FEED_CHECK:-/usr/local/bin/census-fed-check}
START=${FEED_START:-systemctl start}; RUNMAN=${FEED_RUNMAN:-1}; MINMEM=${MINMEM_GB:-64}
DRY=0; [ "${1:-}" = --dry-run ] && DRY=1
ST=/run/census-fed-feeder.status; [ -n "${FED_DIR:-}" ] && ST=$FED/feeder.status
LOGF=/data/logs/fed-feeder.log; [ -n "${FED_DIR:-}" ] && LOGF=$FED/feeder.log
mkdir -p $FED; touch $FED/queue $FED/started
exec 9>$FED/lock; flock -n 9 || { echo "another feeder holds $FED/lock"; exit 0; }
say() { echo "[$(date -u +%FT%TZ)] feeder: $*" | tee -a $LOGF; }
status() { echo "$(date -u +%FT%TZ) $*" > $ST; echo "$*"; }
pause() { echo "$(date -u +%FT%TZ) $*" > $FED/PAUSE; say "PAUSE: $*"; status "paused: $*"; exit 1; }
# demand of one running part: the workers it still uses, min(its workers, running + not started) from
# census-steps --counts; unreadable counts = all its workers. FEED_COUNTS (test) replaces the counts.
demand() {  # $1 ctp dir, $2 run manifest, $3 workers
  local r p; read -r r p < <(echo "${FEED_COUNTS:-$(/usr/local/bin/census-steps --counts "$1" "$2" 2>/dev/null || echo '? ?')}")
  case "$r$p" in *[!0-9]*|'') echo $3; return ;; esac
  local d=$((r + p)); [ $d -gt $3 ] && d=$3; echo $d
}
running() {  # prints "<running parts> <workers in use>"
  local n=0 w=0 i
  if [ -n "$B5_ENV" ] && [ -f "$B5_ENV" ]; then for i in $(. "$B5_ENV"; echo $IDS); do
    fed_active census-b5@$i.service || continue; n=$((n+1))
    w=$((w + $(. /etc/cregit-census/s5/$i.env; demand "$CTP" /home/ec2-user/s5-input/manifest.$i.run.tsv ${WORKERS:-4})))
  done; fi
  for i in $(cat $FED/started); do fed_active "$(printf "$UNIT" $i)" || continue; n=$((n+1))
    w=$((w + $( (. $FED/$i.env 2>/dev/null; demand "${CTP:-/nonexistent}" "${IN:-/nonexistent}/manifest.$i.run.tsv" ${WORKERS:-4}) )))
  done
  echo "$n $w"
}
# slots: the most parts that run at once (default 8); worker_slots: the most workers in use (default 20,
# the 5 parts of 4 workers of batch 5). A part whose last projects run (its other workers idle) counts
# only its busy workers, so the next part starts in the idle workers instead of after the whole tail.
slots=$(cat $FED/slots 2>/dev/null || echo 8); wslots=$(cat $FED/worker_slots 2>/dev/null || echo 20)
q=$(grep -c . $FED/queue || true)
[ -e /run/census-spot-interrupted ] && { status "holding: spot interruption notice ($(cat /run/census-spot-interrupted)); queue $q"; exit 0; }
[ -e $FED/PAUSE ] && { status "paused: $(cat $FED/PAUSE); queue $q"; exit 0; }
started=0
while :; do
  q=$(grep -c . $FED/queue || true); read -r r wu < <(running)
  [ "$q" -gt 0 ] || { status "idle: queue empty; running $r of $slots parts, $wu of $wslots workers"; break; }
  [ "$r" -lt "$slots" ] || { status "waiting: running $r of $slots parts ($wu of $wslots workers); queue $q (next $(head -1 $FED/queue))"; break; }
  [ $((wu + 4)) -le "$wslots" ] || { status "waiting: $wu of $wslots workers in use, running $r parts; queue $q (next $(head -1 $FED/queue))"; break; }
  mem=$(awk '/MemAvailable/{printf "%d", $2/1048576}' /proc/meminfo)
  [ "$mem" -ge "$MINMEM" ] || { status "waiting: MemAvailable ${mem}G < ${MINMEM}G; running $r of $slots parts, $wu of $wslots workers; queue $q"; break; }
  read -r wl p < <(head -1 $FED/queue); id=$wl$p
  cc=$(. $FED/wl/$wl.env 2>/dev/null; echo ${CREGIT_COMMIT:-unset})
  case $cc in pending|unset) status "waiting: the cregit commit of $wl is $cc (census-fed-workload $wl); running $r of $slots parts, $wu of $wslots workers; queue $q (next $id)"; break ;; esac
  if [ $DRY = 1 ]; then status "dry run: would start $id (running $r of $slots parts, $wu of $wslots workers, queue $q)"; break; fi
  say "starting $id: running $r of $slots parts, $wu of $wslots workers, queue $q, MemAvailable ${mem}G"
  out=$($INIT $wl $p 2>&1) || pause "part-init of $id failed: $(echo "$out" | tail -2 | tr '\n' ' ')"
  say "$out"
  if [ "$RUNMAN" = 1 ]; then
    . $FED/$id.env
    oks "$BUCKET/$wl/$p/done/" > $IN/done.$id.txt
    left=$(python3 -I - $IN $id <<'P'
import sys, datetime
I, pid = sys.argv[1], sys.argv[2]
now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
lines = open(f"{I}/manifest.{pid}.tsv").read().splitlines()
cols = next(l for l in lines if l.startswith("# Columns:"))
rows = [l for l in lines if l.strip() and not l.startswith("#")]
done = set(open(f"{I}/done.{pid}.txt").read().split())
keep = [r for r in rows if r.split("\t")[0] not in done]
with open(f"{I}/manifest.{pid}.run.tsv", "w") as f:
    f.write(f"# Run manifest of fed part {pid}, written {now} by census-fed-feeder: {len(keep)} of {len(rows)}"
            f" projects; {len(rows) - len(keep)} already in done/ are left out. u order kept.\n{cols}\n")
    f.writelines(r + "\n" for r in keep)
print(len(keep))
P
) || pause "run manifest of $id failed"
    chown ec2-user: $IN/manifest.$id.run.tsv $IN/done.$id.txt
    if [ "$left" = 0 ]; then say "$id: every project has done/OK; dropped from the queue"; sed -i '1d' $FED/queue; continue; fi
    say "$id: run manifest $left projects"
  fi
  out=$($CHECK $id 2>&1) || pause "identity check of $id failed: $(echo "$out" | tail -1)"
  say "$id: $(echo "$out" | tail -1)"
  echo $id >> $FED/started
  sed -i '1d' $FED/queue
  $START "$(printf "$UNIT" $id)" || pause "start of $(printf "$UNIT" $id) failed"
  started=$((started+1))
  say "started $(printf "$UNIT" $id) $(date -u +%FT%TZ)"
done
[ $started -gt 0 ] && say "started $started part(s) this pass"
exit 0
EOF_census-fed-feeder
chmod 755 /usr/local/bin/census-fed-feeder.new
mv -f /usr/local/bin/census-fed-feeder.new /usr/local/bin/census-fed-feeder
cat > /usr/local/bin/census-fed-finalize.new <<'EOF_census-fed-finalize'
#!/usr/bin/env bash
# census-fed-finalize ID [--dry-run|--decide-only] (census-fed-finalize@ID.service; OnSuccess=/OnFailure= of
# census-fed@ID; 2026-10-09 ~20:10 UTC, made from census-b5-finalize for ONE part). It runs
# census-fed-upload once more, copies the part's results to s3://BUCKET/<workload>/<part>/final/<instance-id>/
# (Parquet and .validated per project, the ctp ledger, duckdb, state json and logs, the census log, the
# part and run manifests, env, cfg, check result, the workload's cregit file), checks every object (key
# and size) and that SHA256SUMS reads back byte-identical, and writes DONE there; when every project of
# the part manifest has done/<project>/OK it also writes <workload>/<part>/final/DONE. Then it runs the
# feeder (the next queued part starts in this slot), and terminates the instance (shutdown; shutdown
# behavior terminate) only if EVERY census on it has finalized: census-spot-decide (b3, b5 and fed:
# no fed unit active, the queue empty, every started fed part with its DONE).
# No shutdown if the copy failed, with --dry-run, if the part ran < 1 h and none of its projects reached
# done/OK (an early failure), or if /home/ec2-user/NO_SHUTDOWN exists.
# After a real spot notice (/run/census-spot-interrupted) it copies nothing: done/ has every finished
# project and restart_spot.sh relaunches the rest.
# --dry-run: copy to <workload>/<part>/dryrun/<instance-id>/ without waiting, never shut down.
# --decide-only: print only the termination decision (census-spot-decide), copy nothing.
# Test overrides: FED_DIR, FED_INPUT (census-fed-common).
set -uo pipefail
. /usr/local/bin/census-fed-common
ID=${1:?id}
DRY=0; [ "${2:-}" = --dry-run ] && DRY=1
DECIDE=0; [ "${2:-}" = --decide-only ] && DECIDE=1
B=$BUCKET
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
FLOG=/data/logs/finalize-fed-$ID.log; TM=$(mktemp -d /tmp/finalize-fed.XXXXXX)
exec > >(tee -a "$FLOG") 2>&1
say() { echo "[$(date -u +%FT%TZ)] finalize-fed $ID: $*"; }
FED_ENV() { . $FED/$1.env; }
if [ $DECIDE = 1 ]; then why=$(/usr/local/bin/census-spot-decide 2>&1); rc=$?
  say "decide-only: $why -> $([ $rc = 0 ] && echo 'would terminate' || echo 'no termination')"; exit 0; fi
FED_ENV $ID
say "start dry=$DRY spot $HALF part $ID ($WL/$PART)"
if [ $DRY = 0 ] && [ -e /run/census-spot-interrupted ]; then
  say "spot interruption notice seen ($(cat /run/census-spot-interrupted)): no final copy; done/ has the finished projects; restart with restart_spot.sh $HALF"
  aws s3 cp "$FLOG" "$B/$WL/$PART/live/finalize-fed.log" --only-show-errors; exit 0
fi
sudo -u ec2-user /usr/local/bin/census-fed-upload || say "census-fed-upload returned $? (continuing)"
finalize_part() {  # $1 = id; returns 1 on a failed copy or check
  local id=$1 n=0 S_ DEST d name files f; FED_ENV $id
  DEST=$B/$WL/$PART/final/$IID; [ $DRY = 1 ] && DEST=$B/$WL/$PART/dryrun/$IID
  pfail() { say "$id FAILED: $*"; echo "finalize failed at $(date -u +%FT%TZ): $*" > "$TM/FINALIZE_FAILED.$id"
            aws s3 cp "$TM/FINALIZE_FAILED.$id" "$DEST/FINALIZE_FAILED" --only-show-errors; return 1; }
  local svc="census-fed@$id: $(systemctl show census-fed@$id.service -p Result -p ExecMainStatus -p ExecMainExitTimestamp 2>/dev/null | tr '\n' ' ')"
  S_=$MP/final-stage; [ -d "$S_" ] && mv "$S_" "$S_.old.$(date +%s)"
  mkdir -p "$S_/projects" "$S_/ctp" "$S_/logs" || { pfail "staging dir"; return 1; }
  for d in "$OUT"/*/; do
    [ -d "$d" ] || continue
    name=$(basename "$d"); [ "$name" = .pin-staging ] && continue
    files=$(find "$d" -maxdepth 1 -type f \( -name '*.parquet' -o -name '*.validated' -o -name '*-persons.db' \))
    [ -n "$files" ] || continue
    mkdir -p "$S_/projects/$name"; for f in $files; do cp -l "$f" "$S_/projects/$name/" 2>/dev/null || cp -p "$f" "$S_/projects/$name/" || { pfail "copy $f"; return 1; }; done; n=$((n+1))
  done
  for f in ledger.jsonl ctp.duckdb metrics.tsv resources.tsv runs.log; do [ -f "$CTP/$f" ] && { cp -p "$CTP/$f" "$S_/ctp/" || { pfail "copy $f"; return 1; }; }; done
  if [ -d "$CTP/state" ]; then
    ( cd "$CTP" && find state -maxdepth 1 -mindepth 1 -type d | while read -r s; do
        mkdir -p "$S_/ctp/$s/logs"; find "$s" -maxdepth 1 -type f -name '*.json' -exec cp -p {} "$S_/ctp/$s/" \;
        [ ! -d "$s/logs" ] || find "$s/logs" -maxdepth 1 -type f -exec cp -p {} "$S_/ctp/$s/logs/" \; ; done ) || { pfail "copy state"; return 1; }
  fi
  [ -f "$LOG" ] && cp -p "$LOG" "$S_/logs/"
  cp -p $IN/manifest.$id.tsv $IN/manifest.$id.run.tsv $FED/$id.env $FED/$id.cfg $FED/$id.check $FED/wl/$WL.env "$S_/logs/" 2>/dev/null
  ( cd "$S_" && find . -type f ! -name SHA256SUMS -printf '%P\0' | sort -z | xargs -0 -r sha256sum > SHA256SUMS ) || { pfail "sha256"; return 1; }
  say "$id: staged $(wc -l < "$S_/SHA256SUMS") files ($n projects), $(du -sh "$S_" | cut -f1) -> $DEST"
  aws s3 cp "$S_/" "$DEST/" --recursive --only-show-errors --checksum-algorithm SHA256 || { pfail "upload"; return 1; }
  ( cd "$S_" && find . -type f -printf '%P\t%s\n' | sort ) > "$TM/final.local.$id"
  aws s3 ls "$DEST/" --recursive | awk -v p="${DEST#s3://*/}/" '{k=$0; sub(/^[^ ]+ +[^ ]+ +[0-9]+ /,"",k); sub("^" p,"",k); print k "\t" $3}' | grep -v -e '^DONE	' -e '^FINALIZE_FAILED	' | sort > "$TM/final.remote.$id" || { pfail "list"; return 1; }
  local missing; missing=$(comm -23 "$TM/final.local.$id" "$TM/final.remote.$id" | wc -l)
  [ "$missing" = 0 ] || { comm -23 "$TM/final.local.$id" "$TM/final.remote.$id" | head; pfail "$missing staged files are missing or differ in size in $DEST"; return 1; }
  aws s3 cp "$DEST/SHA256SUMS" "$TM/final.sums.$id" --only-show-errors && cmp "$TM/final.sums.$id" "$S_/SHA256SUMS" || { pfail "SHA256SUMS read-back differs"; return 1; }
  ( cd "$S_" && sha256sum --quiet -c SHA256SUMS ) || { pfail "staged files changed during upload"; return 1; }
  say "$id: check ok: $(wc -l < "$TM/final.local.$id") objects, sizes equal, SHA256SUMS read back identical"
  { echo "cregit census $WL part $PART ($id) finished and copied: $(date -u +%FT%TZ)"
    echo "instance: $IID  spot $HALF  dry_run=$DRY  cregit $CREGIT_COMMIT"
    echo "$svc"
    echo "projects copied: $n   files: $(wc -l < "$S_/SHA256SUMS")   uploaded to done/ by this instance: $(ls $MP/uploaded 2>/dev/null | wc -l)"
    (cd "$CTP" && CTP_CONFIG=$CFG .venv/bin/python ctp.py progress --manifest $IN/manifest.$id.run.tsv --last 3 2>&1 | head -5)
    echo "--- SHA256SUMS"; cat "$S_/SHA256SUMS"; } > "$TM/DONE.$id"
  aws s3 cp "$TM/DONE.$id" "$DEST/DONE" --only-show-errors && aws s3 ls "$DEST/DONE" >/dev/null || { pfail "DONE upload"; return 1; }
  say "$id: DONE written to $DEST/DONE"
  [ $DRY = 0 ] && cp "$TM/DONE.$id" $MP/final-DONE
  local want have left
  want=$(grep -v -e '^#' -e '^[[:space:]]*$' $IN/manifest.$id.tsv | cut -f1 | sort -u)
  have=$(aws s3 ls "$B/$WL/$PART/done/" --recursive | awk '$4 ~ /\/OK$/ {n=split($4,a,"/"); print a[n-1]}' | sort -u)
  left=$(comm -23 <(echo "$want") <(echo "$have") | grep -c . || true)
  if [ "$left" = 0 ] && [ $DRY = 0 ]; then
    aws s3 cp "$TM/DONE.$id" "$B/$WL/$PART/final/DONE" --only-show-errors && say "$id: every project of the part has done/OK: wrote $B/$WL/$PART/final/DONE"
  else say "$id: $left projects of the part have no done/OK yet (restart_spot.sh $HALF runs them)"; fi
  return 0
}
bad=""
finalize_part $ID || bad=" $ID"
aws s3 cp "$FLOG" "$B/$WL/$PART/$([ $DRY = 1 ] && echo dryrun || echo final)/$IID/finalize-fed.log" --only-show-errors
if [ $DRY = 1 ]; then why=$(/usr/local/bin/census-spot-decide 2>&1); rc=$?
  say "dry run: no shutdown (a real run would: $why -> $([ $rc = 0 ] && echo terminate || echo 'no termination'))"; exit 0; fi
[ -z "$bad" ] || { say "the final copy failed: no shutdown and no new part from here; look at $FLOG"; exit 1; }
/usr/local/bin/census-fed-feeder || say "census-fed-feeder returned $? (see /data/logs/fed-feeder.log)"
st=$(systemctl show census-fed@$ID.service -p ExecMainStartTimestampMonotonic --value); ex=$(systemctl show census-fed@$ID.service -p ExecMainExitTimestampMonotonic --value)
ran=$(( (${ex:-0} - ${st:-0}) / 1000000 )); up=$(ls $MP/uploaded 2>/dev/null | wc -l)
if [ "$ran" -lt 3600 ] && [ "$up" = 0 ]; then say "the part ran only ${ran}s (< 1 h) and none of its projects reached done/OK: an early failure, so no shutdown; look at $LOG"; exit 0; fi
if [ -e /home/ec2-user/NO_SHUTDOWN ]; then say "/home/ec2-user/NO_SHUTDOWN exists: no shutdown"; exit 0; fi
if ! why=$(/usr/local/bin/census-spot-decide 2>&1); then say "$why: no shutdown; the last census on this instance to finalize terminates it"; exit 0; fi
say "$why"
say "shutting down: this one-time spot instance terminates (shutdown behavior terminate)"
sync; shutdown -h now
EOF_census-fed-finalize
chmod 755 /usr/local/bin/census-fed-finalize.new
mv -f /usr/local/bin/census-fed-finalize.new /usr/local/bin/census-fed-finalize
echo "s6 files 1 installed"
