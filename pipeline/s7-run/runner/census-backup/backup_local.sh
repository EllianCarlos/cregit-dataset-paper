#!/usr/bin/env bash
# backup_local.sh (2026-10-09, user request): back up the finished local batch 1 Parquets to
# s3://BUCKET/batch1/done/<project>/ (Parquet, .validated, persons files, then OK with the Parquet
# sha256), skipping projects that already have OK. Also copies the ctp ledger, metrics.tsv and
# resources.tsv to batch1/backup-ledger/. Read-only on the census. Start it as the user (Claude's
# aws s3 cp is denied by the permission system), once or from the user timer in README.md.
set -uo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
here=$(dirname "$(readlink -f "$0")")
exec 9>"$here/.local.lock"; flock -n 9 || exit 0
B=s3://${RUNNER_BUCKET}; run=batch1
out=${RUNNER_PROJECTS}/cregit-workspace/census-2026-10
ctp=${RUNNER_PROJECTS}/cregit-token-pipeline/.claude/worktrees/agent-a0a3254f563a6a4b5
log=$here/backup-local.log
ts() { date -u +%FT%TZ; }
have=$(aws s3 ls "$B/$run/done/" --recursive 2>/dev/null | awk '/\/OK$/{print $4}')
new=0; fail=0
for v in "$out"/*/*.validated; do
  [ -e "$v" ] || continue
  d=$(dirname "$v"); p=$(basename "$d")
  case "$p" in .*) continue ;; esac
  grep -qx "$run/done/$p/OK" <<<"$have" && continue
  pq="$d/$p-dataset.parquet"; [ -s "$pq" ] || continue
  ok=1
  for f in "$pq" "$v" "$d/$p-persons.db" "$d/$p-persons.xls"; do
    [ -e "$f" ] || continue
    key="$run/done/$p/$(basename "$f")"
    nice -n 10 aws s3 cp "$f" "$B/$key" --only-show-errors || { ok=0; break; }
    rs=$(aws s3api head-object --bucket "${B#s3://}" --key "$key" --query ContentLength --output text 2>/dev/null)
    [ "$rs" = "$(stat -c %s "$f")" ] || { ok=0; break; }
  done
  if [ $ok = 1 ]; then
    printf '%s  %s\nbacked_up=%s\n' "$(sha256sum "$pq" | cut -d' ' -f1)" "$(basename "$pq")" "$(ts)" \
      | aws s3 cp - "$B/$run/done/$p/OK" --only-show-errors && new=$((new + 1))
  else fail=$((fail + 1)); echo "$(ts) $p: upload or size check FAILED" >> "$log"; fi
done
for f in ledger.jsonl metrics.tsv resources.tsv; do
  [ -e "$ctp/$f" ] && aws s3 cp "$ctp/$f" "$B/$run/backup-ledger/$f" --only-show-errors
done
echo "$(ts) pass done: new=$new failed=$fail" | tee -a "$log"
