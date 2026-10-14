# post-relaunch.remote.sh: the instance half of ../post_relaunch.sh. post_relaunch.sh puts
# "X=<a|b>" and "WAIT=<seconds>" in front of this file and runs the result as root with ssm.sh.
# Three steps after a spot relaunch. Each step checks first, changes only what it must, and skips
# (prints SKIP) when the state is not the expected one. A second run changes nothing.
#   slots:  spot a only. Writes /etc/cregit-census/fed/slots = 12 (temp file + mv) when the file is
#           absent or holds 8, and the instance has at least 700 GiB of memory.
#   copies: both halves. For each active census-b3@/census-b5@/census-fed@ part, finds its cregit
#           copy (b3: cregit_dir of /etc/cregit-census/<part>.cfg; b5: CREGIT of
#           /etc/cregit-census/s5/<id>.env; fed: CREGIT of /etc/cregit-census/fed/<id>.env) and
#           replaces blameRepo/formatBlame.pl with the 57551d7 file only when the copy holds the old
#           file (install to a temp name + mv). Never changes the template /data/cregit-ec2. Waits
#           up to WAIT seconds for a copy that does not exist yet.
#   queue:  spot a only. Removes "batch22 a3" and "batch21 a5" from the fed queue under the feeder
#           lock (flock -w 3000), only when both are queued, not started and not active.
set -uo pipefail
: "${X:?}" "${WAIT:=600}"
F=/etc/cregit-census/fed; E=/etc/cregit-census
NEW=788acb9abac05782058c6b0b599b349caf63b85fa49b8375af9240be7bc0b435
OLD=bcb806793422aac1cb039a73e355036944e4bcab8af6ea3184d7e235f3678f53
COMMIT=57551d7ad82a784615c1490623d72cb9dc994ba1
BUNDLE=s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle
BUNDLE_SHA=18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e
W=/root/post-relaunch; NEWF=$W/formatBlame.pl.$COMMIT
id=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
say() { echo "post_relaunch $X $id $(date -u +%FT%TZ) $*"; }
rc=0
half=$(cat $F/half 2>/dev/null || echo none)
[ "$half" = "$X" ] || { say "ABORT: $F/half is '$half', not '$X': nothing changed"; exit 1; }
sha() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }

# --- slots (spot a only)
if [ "$X" = a ]; then
  cur=$(cat $F/slots 2>/dev/null || echo absent)
  memg=$(awk '/MemTotal/ {print int($2/1048576)}' /proc/meminfo)
  if [ "$cur" = 12 ]; then say "slots: already 12: nothing to do"
  elif [ "$cur" != absent ] && [ "$cur" != 8 ]; then say "slots: SKIP: the file holds '$cur' (not absent, 8 or 12): set by hand?"
  elif [ "$memg" -lt 700 ]; then say "slots: SKIP: MemTotal ${memg} GiB < 700 GiB: keep the default; decide by hand"
  else
    echo 12 > $F/slots.post-relaunch.tmp && chmod 644 $F/slots.post-relaunch.tmp && mv -f $F/slots.post-relaunch.tmp $F/slots
    [ "$(cat $F/slots)" = 12 ] && say "slots: $cur -> 12 (MemTotal ${memg} GiB)" || { say "slots: FAILED to write"; rc=1; }
  fi
fi

# --- copies (both halves)
tpl=$(readlink -f /data/cregit-ec2)
# copy_of UNIT: print the cregit copy of an active part unit, or nothing
copy_of() {
  local u=$1 inst=${1#*@}; inst=${inst%.service}
  case $u in
    census-b3@*) sed -n 's/^cregit_dir *= *//p' "$E/$inst.cfg" 2>/dev/null | head -1 ;;
    census-b5@*) sed -n 's/^CREGIT=//p' "$E/s5/$inst.env" 2>/dev/null | head -1 ;;
    census-fed@*) sed -n 's/^CREGIT=//p' "$F/$inst.env" 2>/dev/null | head -1 ;;
  esac
}
get_new() {
  [ "$(sha "$NEWF")" = "$NEW" ] && return 0
  # The bundle needs the 95cdc88 history: a scratch clone of the template (read only) gets it.
  mkdir -p $W; local s; s=$(mktemp -d /tmp/post-relaunch.XXXXXX); chown ec2-user: "$s"
  aws s3 cp --only-show-errors "$BUNDLE" "$s/b.bundle" || { say "copies: FAILED to fetch the bundle"; rm -rf "$s"; return 1; }
  [ "$(sha "$s/b.bundle")" = "$BUNDLE_SHA" ] || { say "copies: bundle sha256 $(sha "$s/b.bundle") is wrong"; rm -rf "$s"; return 1; }
  chown ec2-user: "$s/b.bundle"
  sudo -u ec2-user git clone -q --no-checkout --no-hardlinks "$tpl" "$s/r" \
    && sudo -u ec2-user git -C "$s/r" fetch -q "$s/b.bundle" "+refs/heads/*:refs/bundle/*" \
    && sudo -u ec2-user git -C "$s/r" show "$COMMIT:blameRepo/formatBlame.pl" > $NEWF.tmp \
    || { say "copies: FAILED to read formatBlame.pl of $COMMIT from the bundle"; rm -rf "$s" $NEWF.tmp; return 1; }
  rm -rf "$s"
  [ "$(sha $NEWF.tmp)" = "$NEW" ] || { say "copies: the bundle file has sha256 $(sha $NEWF.tmp), not $NEW"; rm -f $NEWF.tmp; return 1; }
  mv -f $NEWF.tmp $NEWF
}
t_end=$(( $(date +%s) + WAIT ))
while :; do
  missing=""; nnew=0; nswap=0; nskip=0
  units=$(systemctl list-units --no-legend --plain --state=active,activating 'census-b3@*' 'census-b5@*' 'census-fed@*' | awk '{print $1}')
  [ -n "$units" ] || say "copies: no active census-b3@/census-b5@/census-fed@ part"
  for u in $units; do
    d=$(copy_of "$u")
    [ -n "$d" ] || { say "copies: SKIP $u: no cregit copy in its config"; nskip=$((nskip+1)); continue; }
    f=$d/blameRepo/formatBlame.pl
    [ -f "$f" ] || { missing="$missing $u"; continue; }
    if [ "$(readlink -f "$d")" = "$tpl" ]; then say "copies: SKIP $u: it uses the template $d (= $tpl); the template is never changed"; nskip=$((nskip+1)); continue; fi
    s=$(sha "$f")
    if [ "$s" = "$NEW" ]; then nnew=$((nnew+1)); say "copies: $u $d: already new (${NEW:0:16})"; continue; fi
    [ "$s" = "$OLD" ] || { say "copies: SKIP $u $d: unexpected sha256 $s"; nskip=$((nskip+1)); continue; }
    get_new || { rc=1; break 2; }
    tmp=$d/blameRepo/.formatBlame.pl.post-relaunch.$$
    install -o "$(stat -c %U "$f")" -g "$(stat -c %G "$f")" -m "$(stat -c %a "$f")" $NEWF "$tmp" && mv -f "$tmp" "$f"
    if [ "$(sha "$f")" = "$NEW" ]; then nswap=$((nswap+1)); say "copies: SWAPPED $u $d (${OLD:0:16} -> ${NEW:0:16})"
    else say "copies: FAILED $u $d: sha256 now $(sha "$f")"; rm -f "$tmp"; rc=1; fi
  done
  [ -z "$missing" ] && break
  [ "$(date +%s)" -lt $t_end ] || { say "copies: SKIP: no copy yet after ${WAIT}s for:$missing (run post_relaunch.sh again)"; break; }
  say "copies: waiting for the copy of:$missing"; sleep 30
done
say "copies: $nswap swapped, $nnew already new, $nskip skipped"

# --- queue (spot a only)
if [ "$X" = a ]; then
  items=("batch22 a3" "batch21 a5")
  n=0; for it in "${items[@]}"; do grep -qx "$it" $F/queue && n=$((n+1)); done
  if [ $n = 0 ]; then say "queue: batch22 a3 and batch21 a5 are not queued: nothing to do"
  elif [ $n = 1 ]; then say "queue: SKIP: only one of batch22 a3 / batch21 a5 is queued: nothing changed"
  else
    say "queue: both queued; waiting for the feeder lock (flock -w 3000)"
    (
      exec 9>$F/lock; flock -w 3000 9 || { say "queue: LOCK TIMEOUT: nothing changed"; exit 1; }
      for it in "${items[@]}"; do i=$(echo $it | tr -d ' ')
        grep -qx "$it" $F/queue || { say "queue: ABORT: $it is no longer queued: nothing changed"; exit 1; }
        grep -qx "$i" $F/started && { say "queue: ABORT: $i is in started: nothing changed"; exit 1; }
        systemctl is-active -q census-fed@$i.service && { say "queue: ABORT: census-fed@$i is active: nothing changed"; exit 1; }
      done
      n0=$(grep -c . $F/queue)
      grep -vx -e "batch22 a3" -e "batch21 a5" $F/queue > $F/queue.post-relaunch.tmp
      n1=$(grep -c . $F/queue.post-relaunch.tmp)
      [ $((n0 - n1)) = 2 ] || { rm -f $F/queue.post-relaunch.tmp; say "queue: ABORT: $n0 -> $n1 lines, not 2 fewer: nothing changed"; exit 1; }
      chmod 644 $F/queue.post-relaunch.tmp; mv -f $F/queue.post-relaunch.tmp $F/queue
      say "queue: removed batch22 a3 and batch21 a5 ($n0 -> $(grep -c . $F/queue) lines)"
    ) || rc=1
  fi
fi
say "feeder: $(cat /run/census-fed-feeder.status 2>/dev/null)"
say "done rc=$rc"
exit $rc
