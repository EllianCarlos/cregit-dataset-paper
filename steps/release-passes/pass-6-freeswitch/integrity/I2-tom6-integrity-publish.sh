#!/usr/bin/env bash
# I2-tom6-integrity-publish.sh (the TOM-6 machine, root, through ssm-tom6.sh; EXPORTS="ACTION=plan|publish"): adds the
# report of I1 to the published root as docs/INTEGRITY.md and docs/integrity.tsv (the layout of the release docs/).
#   ACTION=plan    (default) builds the publish root and the new SHA256SUMS and checks them; writes nothing to S3 or
#                  to Hugging Face
#   ACTION=publish 1. S3: a copy of the old SHA256SUMS to DEST/integrity/run-<utc>/SHA256SUMS.before, the two docs
#                     files to DEST/root/docs/, then the new SHA256SUMS (last); then the S3 SHA256SUMS must be the new one
#                  2. Hugging Face: the token from SSM to tmpfs; the Hub must be the old root (hf_tools.py verify); ONE
#                     commit with the 3 changed files (hf_tools.py upload of the kit: it uploads only the files that
#                     are not on the Hub); verify of the whole tree against the new SHA256SUMS; the token file deleted.
#                     Visibility never changes; no DOI.
# MANIFEST.tsv lists only parquet/ files, so it does not change. A second run continues (a done step is skipped).
# It refuses: another instance, a running unit, an integrity run that is not DONE with 0 problems, a changed S3 root.
set -uo pipefail
WANT_IID=${WANT_IID:?set EXPORTS="WANT_IID=<the instance id of the TOM-6 machine>"}
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag 2>/dev/null)
[ "$IID" = "$WANT_IID" ] || { echo "ABORT: this is $IID, not the TOM-6 machine $WANT_IID"; exit 1; }
X=${TOM_X:-/data/tom6}; T=$X/tools; PY=$X/venv/bin/python
. $T/tom6.conf
W=${INTEG_DIR:-/data1/integrity}
B=s3://$BUCKET; ROOT=$B/$DEST/root; IP=$B/$DEST/integrity
ACTION=${ACTION:-plan}
DOCS="docs/INTEGRITY.md docs/integrity.tsv"
TOK=$HF_TOKEN_DIR/token
fail() { rm -f $TOK; echo "ABORT: $*"; exit 1; }
case $ACTION in plan|publish) ;; *) fail "ACTION is plan or publish" ;; esac
AS="runuser -u ec2-user -- env HOME=/home/ec2-user AWS_REGION=us-west-2 AWS_RETRY_MODE=adaptive AWS_MAX_ATTEMPTS=10 PYTHONDONTWRITEBYTECODE=1"

# ---- guards
for u in tom6-run tom6-integrity; do systemctl is-active -q $u && fail "the unit $u runs"; done
[ -f $X/status/run.DONE ] || fail "the release run is not DONE"
[ "$HF" != 1 ] || [ -f $X/status/hf.DONE ] || fail "the release run has no hf.DONE (the Hub must hold the new root first)"
grep -q '^DONE ' $W/status/state 2>/dev/null || fail "the integrity run is not DONE: $(cat $W/status/state 2>/dev/null)"
STAMP=$(cat $W/status/last_run) || fail "no $W/status/last_run"
J=$W/out/integrity.json
read -r nprob checked < <($PY -I -c "import json,sys; d=json.load(open(sys.argv[1])); print(d['problems_total'], d['sha256sums_sha256'])" $J) \
  || fail "no $J"
[ "$nprob" = 0 ] || fail "the integrity report has $nprob problems; this script publishes only a report with 0 problems"
(cd $T && grep -E '  (hf_tools.py|release_tools.py|tom6.conf)$' SHA256SUMS | sha256sum --quiet --strict -c -) \
  || fail "a kit tool is not its stage SHA256SUMS row"
[ "$(sha256sum $W/root/SHA256SUMS | cut -d' ' -f1)" = "$checked" ] || fail "the local SHA256SUMS is not the checked one"
for f in INTEGRITY.md integrity.tsv; do
  $AS aws s3 cp $IP/run-$STAMP/$f $W/status/uploaded.$f --only-show-errors || fail "download of $IP/run-$STAMP/$f"
  cmp -s $W/status/uploaded.$f $W/out/$f || fail "$f is not the report of $IP/run-$STAMP/"
done
grep -q "^| Result | \*\*0 problems\*\* |" $W/out/INTEGRITY.md || fail "INTEGRITY.md does not say 0 problems"
grep -q '  docs/INTEGRITY.md$' $W/root/SHA256SUMS && fail "the checked SHA256SUMS lists docs/INTEGRITY.md already"
$PY -I -c "import csv,sys; r=list(csv.DictReader(open(sys.argv[1]), delimiter='\t')); sys.exit(any(not x['path'].startswith('parquet/') for x in r))" \
  $W/root/MANIFEST.tsv || fail "MANIFEST.tsv lists files outside parquet/ (this script does not update it)"

# ---- the publish root: hard links of the checked root, the two docs files, the new SHA256SUMS
P=$W/publish.$STAMP
if [ ! -f $P/new.sha256 ]; then
  [ -e $P ] && mv $P $P.old.$(date -u +%s)
  $AS mkdir -p $P/root
  $AS cp -al $W/root/. $P/root/ || fail "the hard-link copy"
  for f in INTEGRITY.md integrity.tsv; do $AS cp $W/out/$f $P/root/docs/$f || fail "copy of $f"; done
  $AS $PY -I -B - $P/root $W/root/SHA256SUMS $P/SHA256SUMS.new $DOCS <<'EOF' || fail "the new SHA256SUMS"
import hashlib, sys
from pathlib import Path
root, old, new, docs = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4:]
rows = {}
for line in Path(old).read_text().splitlines():
    if line.strip():
        d, f = line.split("  ", 1)
        assert f not in rows, f
        rows[f] = d
assert not set(docs) & set(rows), "a docs file is in SHA256SUMS already"
for f in docs:
    rows[f] = hashlib.sha256((root / f).read_bytes()).hexdigest()
Path(new).write_text("".join(f"{rows[f]}  {f}\n" for f in sorted(rows)))
print(f"SHA256SUMS: {len(rows) - len(docs)} rows + {len(docs)} = {len(rows)}")
EOF
  $AS mv -f $P/SHA256SUMS.new $P/root/SHA256SUMS || fail "the new SHA256SUMS into the publish root"
  [ "$(sha256sum $W/root/SHA256SUMS | cut -d' ' -f1)" = "$checked" ] || fail "the checked SHA256SUMS changed (hard link)"
  d=$(diff <(grep -vE '  docs/(INTEGRITY\.md|integrity\.tsv)$' $P/root/SHA256SUMS) $W/root/SHA256SUMS | wc -l)
  [ "$d" = 0 ] || fail "the new SHA256SUMS changes $d other rows"
  (cd $P/root && grep -E '  docs/(INTEGRITY\.md|integrity\.tsv)$' SHA256SUMS | sha256sum --quiet --strict -c -) || fail "the docs rows"
  $PY -I -B $T/release_tools.py no-at $P/root/docs/INTEGRITY.md $P/root/docs/integrity.tsv > $P/guards.txt 2>&1 || fail "no-at: $(tail -2 $P/guards.txt)"
  $PY -I -B $T/release_tools.py no-paths $P/root/docs/INTEGRITY.md $P/root/docs/integrity.tsv >> $P/guards.txt 2>&1 || fail "no-paths: $(tail -2 $P/guards.txt)"
  sha256sum $P/root/SHA256SUMS | cut -d' ' -f1 > $P/new.sha256
fi
NEW=$(cat $P/new.sha256)
echo "publish root $P/root: SHA256SUMS ${checked:0:12} -> ${NEW:0:12} ($(wc -l < $P/root/SHA256SUMS) rows); docs: $(for f in $DOCS; do echo -n "$f $(stat -c %s $P/root/$f) B; "; done)"
[ "$ACTION" = plan ] && { echo "plan only: nothing written to S3 or the Hub (ACTION=publish does it)"; exit 0; }

# ---- 1. S3
$AS aws s3 cp $ROOT/SHA256SUMS $P/s3.SHA256SUMS --only-show-errors || fail "download of the S3 SHA256SUMS"
s3sha=$(sha256sum $P/s3.SHA256SUMS | cut -d' ' -f1)
if [ "$s3sha" = "$checked" ]; then
  $AS aws s3 cp $P/s3.SHA256SUMS $IP/run-$STAMP/SHA256SUMS.before --only-show-errors || fail "the copy of the old SHA256SUMS"
  for f in $DOCS; do
    $AS aws s3 cp $P/root/$f $ROOT/$f --checksum-algorithm SHA256 --only-show-errors || fail "the upload of $f"
  done
  $AS aws s3 cp $P/root/SHA256SUMS $ROOT/SHA256SUMS --checksum-algorithm SHA256 --only-show-errors || fail "the upload of SHA256SUMS"
  $AS aws s3 cp $ROOT/SHA256SUMS $P/s3.SHA256SUMS.after --only-show-errors || fail "download of the new S3 SHA256SUMS"
  [ "$(sha256sum $P/s3.SHA256SUMS.after | cut -d' ' -f1)" = "$NEW" ] || fail "the S3 SHA256SUMS is not the new one after the upload"
  echo "S3: $DOCS and SHA256SUMS ${NEW:0:12} in $ROOT/"
elif [ "$s3sha" = "$NEW" ]; then
  echo "S3: done before (the S3 SHA256SUMS is ${NEW:0:12})"
else
  fail "the S3 SHA256SUMS is ${s3sha:0:12}: not the checked ${checked:0:12} and not the new ${NEW:0:12}"
fi
for f in $DOCS; do
  n=$($AS aws s3api head-object --bucket $BUCKET --key $DEST/root/$f --query ContentLength --output text) || fail "head $f"
  [ "$n" = "$(stat -c %s $P/root/$f)" ] || fail "the S3 size of $f is $n"
done

# ---- 2. Hugging Face (the token as in tom6_run.sh: SSM to tmpfs, deleted after)
hf="skipped (HF=$HF)"
if [ "$HF" = 1 ]; then
  [ "$HF_VISIBILITY" = public ] && PRIV="" || PRIV=--private
  install -d -m 700 -o ec2-user -g ec2-user $HF_TOKEN_DIR
  trap 'rm -f $TOK' EXIT
  (umask 077; aws ssm get-parameter --region us-west-2 --name $HF_SSM_PARAM --with-decryption --query Parameter.Value \
     --output text 2>/dev/null | tr -d '[:space:]' > $TOK); chown ec2-user: $TOK
  [ -s $TOK ] || fail "no Hugging Face token in $HF_SSM_PARAM"
  HAS="runuser -u ec2-user -- env HOME=/home/ec2-user HF_HOME=$X/hf-home HF_TOKEN_PATH=$TOK HF_HUB_DISABLE_TELEMETRY=1 HF_HUB_DISABLE_PROGRESS_BARS=1 HF_XET_HIGH_PERFORMANCE=1"
  HT="$PY -I -B $T/hf_tools.py"
  if $HAS $HT verify --repo $HF_REPO --sums $P/root/SHA256SUMS --card $P/root/README.md --out $P/hf-verify.txt \
       --expect $HF_VISIBILITY > $P/hf.txt 2>&1; then
    hf="done before ($(grep -m1 '^repository' $P/hf-verify.txt | cut -c1-120))"
  else
    $HAS $HT verify --repo $HF_REPO --sums $W/root/SHA256SUMS --card $W/root/README.md --out $P/hf-preverify.txt \
      --expect $HF_VISIBILITY >> $P/hf.txt 2>&1 || fail "the Hub is not the checked root: $(tail -3 $P/hf-preverify.txt | cut -c1-200)"
    $HAS $HT upload --repo $HF_REPO $PRIV --root $P/root --card $P/root/README.md >> $P/hf.txt 2>&1 \
      || fail "hf upload: $(tail -3 $P/hf.txt | cut -c1-200)"
    $HAS $HT verify --repo $HF_REPO --sums $P/root/SHA256SUMS --card $P/root/README.md --out $P/hf-verify.txt \
      --expect $HF_VISIBILITY >> $P/hf.txt 2>&1 || fail "hf verify after the upload: $(tail -3 $P/hf-verify.txt | cut -c1-200)"
    hf="pushed: $(grep -E 'to upload|UPLOAD DONE' $P/hf.txt | sed 's/^\[[^]]*\] //' | cut -c1-110 | paste -sd';'); $(grep -m1 '^repository' $P/hf-verify.txt | cut -c1-120)"
  fi
  rm -f $TOK
  [ -e $TOK ] && fail "the token file is still there"
fi
{ echo "{"; echo "  \"utc\": \"$(date -u +%FT%TZ)\","; echo "  \"integrity_run\": \"run-$STAMP\","
  echo "  \"sha256sums_before\": \"$checked\","; echo "  \"sha256sums_after\": \"$NEW\","
  echo "  \"s3\": \"$ROOT/ ($DOCS, SHA256SUMS)\","; echo "  \"hf\": \"$(echo "$hf" | tr '"' "'")\""; echo "}"; } > $P/publish.json
$AS aws s3 cp $P/publish.json $IP/run-$STAMP/publish.json --only-show-errors || echo "WARNING: publish.json upload failed"
cp $P/hf-verify.txt $P/hf.txt $W/status/ 2>/dev/null
echo "Hugging Face: $hf"
echo "I2-tom6 done: SHA256SUMS ${checked:0:12} -> ${NEW:0:12}"
