#!/usr/bin/env bash
# E0-probe-a.sh, machine A (read-only; root through scripts/a/ssm-a.sh): the facts E1 needs, with no
# write anywhere. The step-7 process of aws-sdk-java (jobs, the env names, CREGIT_C100_LIMIT), the git
# and perl binaries of the running blame and their versions (the extras must have the same), the
# cregit tree (HEAD, the 57551d7 blobs), the working clone (HEAD, size, alternates), free disk,
# the memory of the git blame processes of the row, the .blame count and the started lines of
# step 7. Output: counts and paths of tools only.
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
[ "$IID" = ${RUNNER_EC2_X1K_LONG_A4} ] || { echo "ABORT: $IID is not machine A"; exit 1; }
P=aws__aws-sdk-java
main() {
T=$(readlink -f /data/x1k-long/$P); W=$T/out/$P/$P-cregit; PL=$T/out/$P/pipeline.log
echo "== $(date -u +%FT%TZ) E0 on $IID; unit $(systemctl is-active x1k-long@$P); JOBS $(sed -n 's/^JOBS=//p' "$T/run.env")"
echo "newest step heading: $(grep -a -E '^  Step [0-9]+ ' "$PL" | tail -1)"
brf=""; gp=""; ng=0; rss=0; rmax=0
for d in /proc/[0-9]*; do
  a=$(tr '\0' '\n' < "$d/cmdline" 2>/dev/null) || continue
  case "$a" in *blameRepoFiles.pl*) echo "$a" | grep -q -x -F "$W" && brf=${d#/proc/} ;; esac
  if echo "$a" | grep -q -x blame && echo "$a" | grep -q -x -F "$W"; then
    case $(readlink "$d/exe" 2>/dev/null | sed 's#.*/##') in
      git|.git-wrapped|git-*) [ -z "$gp" ] && gp=${d#/proc/}
        # The memory of each git blame of the row (VmRSS, kB): S1 caps the jobs by memory.
        ng=$((ng + 1)); r=$(awk '/^VmRSS:/ {print $2}' "$d/status" 2>/dev/null); rss=$((rss + ${r:-0}))
        [ "${r:-0}" -gt "$rmax" ] && rmax=${r:-0} ;;
    esac
  fi
done
echo "git blame processes of the row: $ng; memory sum $((rss / 1048576)) GiB, mean $((rss / (ng > 0 ? ng : 1) / 1024)) MiB, largest $((rmax / 1024)) MiB"
if [ -n "$brf" ]; then
  echo "blameRepoFiles.pl pid $brf: $(tr '\0' '\n' < /proc/$brf/cmdline | grep -e '^--' | tr '\n' ' ')"
  echo "  exe $(readlink -f /proc/$brf/exe): $("$(readlink -f /proc/$brf/exe)" -e 'print $^V')"
  echo "  env names: $(tr '\0' '\n' < /proc/$brf/environ | grep -E '^(PATH|HOME|LANG|LC_[A-Z]+|PERL5LIB|TZ|CREGIT_[A-Z0-9_]+|GIT_[A-Z0-9_]+)=' | cut -d= -f1 | tr '\n' ' ')"
  echo "  PATH: $(tr '\0' '\n' < /proc/$brf/environ | sed -n 's/^PATH=//p' | cut -c1-300)"
  echo "  CREGIT_C100_LIMIT: $(tr '\0' '\n' < /proc/$brf/environ | sed -n 's/^CREGIT_C100_LIMIT=//p' | grep . || echo 'not set (3600 s)')"
else echo "no blameRepoFiles.pl process of the row"; fi
if [ -n "$gp" ]; then g=$(readlink -f /proc/$gp/exe); echo "git blame pid $gp: exe $g: $("$g" --version)"; else echo "no git blame process of the row"; fi
echo "git on PATH of root: $(command -v git) $(git --version 2>/dev/null)"
C=$T/cregit-ec2
echo "cregit $C: HEAD $(sudo -u ec2-user git -C "$C" rev-parse --short HEAD); formatBlame blob $(sudo -u ec2-user git hash-object "$C/blameRepo/formatBlame.pl" | cut -c1-8) (57551d7: 76d8a379); blameRepoFiles blob $(sudo -u ec2-user git hash-object "$C/blameRepo/blameRepoFiles.pl" | cut -c1-8) (57551d7: 7036ef5a)"
echo "cregit tree size (without build dirs): $(du -sb --exclude=build "$C" | awk '{print int($1 / 1000000)}') MB"
echo "working clone: HEAD $(sudo -u ec2-user git -C "$W" rev-parse --short HEAD); alternates: $([ -e "$W/.git/objects/info/alternates" ] && echo YES || echo no); size $(du -sb "$W" | awk '{print int($1 / 1000000)}') MB (.git $(du -sb "$W/.git" | awk '{print int($1 / 1000000)}') MB)"
echo ".blame files: $(find "$T/out/$P/blame" -name '*.blame' | wc -l); started lines in pipeline.log: $(grep -a -c -E '^[0-9]+: ' "$PL"); PLAIN-BLAME lines: $(grep -a -c '^PLAIN-BLAME ' "$PL")"
df -h --output=target,size,avail /data1 /data3 | sed 's/^/  /'
uptime; free -g | sed -n 2p
echo "S3 java-split/: $(aws s3 ls s3://${RUNNER_BUCKET}/dataset-x1k/java-split/ 2>/dev/null | wc -l) entries"
}
main 2>&1 | sed -u 's/@//g'
