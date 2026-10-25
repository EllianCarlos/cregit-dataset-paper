#!/usr/bin/env bash
# T1-dry-run.sh (this machine, no AWS): dry run of the deal of R4-start-pf.sh and of pf-seed of
# R3-install-pf.sh on the staged inputs (stage/inputs/, the files that U1-upload-pathfix.sh uploaded).
# It takes the embedded Python of the two scripts as it is (sed between the heredoc markers) and
# runs it in a new temp folder; the S3 seeds come from a synthetic local done-full/ folder.
# Prints PASS/FAIL per case and "T1 ALL PASS" at the end.
set -uo pipefail
H=$(cd "$(dirname "$0")/../.." && pwd)
S=$H/scripts; IN=$H/stage/inputs
T=$(mktemp -d /tmp/pf-dry.XXXXXX); echo "temp folder $T"
sed -n "/<<'PY_DEAL'/,/^PY_DEAL\$/p" $S/R4-start-pf.sh | sed '1d;$d' > $T/deal.py
sed -n "/<<'EOF_pf_seed'/,/^EOF_pf_seed\$/p" $S/R3-install-pf.sh | sed '1d;$d' > $T/pf-seed
[ -s $T/deal.py ] && [ -s $T/pf-seed ] || { echo "FAIL: cannot extract the embedded Python"; exit 1; }
(cd $IN && sha256sum --quiet -c SHA256SUMS) || { echo "FAIL: stage/inputs sha256"; exit 1; }
[ "$(sha256sum $IN/SHA256SUMS | cut -d' ' -f1)" = "$(grep -o 'WANT_SUMS=[0-9a-f]*' $S/R4-start-pf.sh | cut -d= -f2)" ] || { echo "FAIL: WANT_SUMS of R4 is not the staged SHA256SUMS"; exit 1; }
fails=0
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; fails=$((fails + 1)); }
rows() { grep -c -v -e '^#' -e '^[[:space:]]*$' "$1"; }
# --- deal, first start (no done-pathfix/OK)
: > $T/oks.none
python3 -I $T/deal.py $IN $T/oks.none $T/deal1 dataset-pathfix-b1 alibaba__AliSQL > $T/deal1.out 2>&1 && cat $T/deal1.out || { cat $T/deal1.out; fail "deal 1 rc"; }
[ "$(rows $T/deal1/manifest.run.p1.tsv)" = 17 ] && [ "$(rows $T/deal1/manifest.run.p2.tsv)" = 18 ] && [ ! -e $T/deal1/manifest.run.p3.tsv ] \
  && pass "deal: p1 17 rows, p2 18 rows, no p3" || fail "deal row counts"
cat $T/deal1/manifest.run.p1.tsv $T/deal1/manifest.run.p2.tsv | grep -v '^#' | cut -f1 | grep -q -x alibaba__AliSQL && fail "AliSQL is in a run manifest" || pass "AliSQL is in no run manifest"
grep -q $'^dropped\t-\talibaba__AliSQL' $T/deal1/deal.tsv && pass "deal.tsv lists AliSQL as dropped" || fail "deal.tsv dropped line"
[ "$(sed -n 3p $T/deal1/manifest.run.p2.tsv | cut -f1)" = linuxkerneltravel__lmp ] && [ "$(sed -n 3p $T/deal1/manifest.run.p1.tsv | cut -f1)" = SpecialKO__SpecialK ] \
  && pass "longest rows first (lmp in p2, SpecialK in p1)" || fail "order"
n35=$(cat $T/deal1/manifest.run.p1.tsv $T/deal1/manifest.run.p2.tsv | grep -v '^#' | cut -f1 | sort -u | wc -l)
want35=$(grep -v -e '^#' $IN/manifest.pathfix.tsv | cut -f1 | grep -v -x alibaba__AliSQL | sort -u | wc -l)
[ "$n35" = 35 ] && [ "$want35" = 35 ] && pass "35 distinct rows = the manifest minus AliSQL" || fail "35 rows ($n35, $want35)"
cmp -s <(cat $T/deal1/manifest.run.p1.tsv $T/deal1/manifest.run.p2.tsv | grep -v '^#' | sort) <(grep -v '^#' $IN/manifest.pathfix.tsv | grep -v '^alibaba__AliSQL	' | sort) \
  && pass "run manifest rows are byte-equal to manifest.pathfix.tsv rows" || fail "row bytes"
# --- deal, relaunch: 2 rows have done-pathfix/OK
printf 'doocs__leetcode\nKSwordDEV__KSword\n' > $T/oks.two
python3 -I $T/deal.py $IN $T/oks.two $T/deal2 dataset-pathfix-b1-r1 alibaba__AliSQL > $T/deal2.out 2>&1
[ "$(rows $T/deal2/manifest.run.p1.tsv)" = 16 ] && [ "$(rows $T/deal2/manifest.run.p2.tsv)" = 17 ] && pass "relaunch deal: 16 + 17 to run" || { cat $T/deal2.out; fail "relaunch deal"; }
# --- deal refuses: AliSQL with OK, an unknown OK, no DROP
echo alibaba__AliSQL > $T/oks.ali
python3 -I $T/deal.py $IN $T/oks.ali $T/deal3 dataset-pathfix-b1 alibaba__AliSQL > $T/deal3.out 2>&1 && fail "deal took an OK of AliSQL" || pass "deal refuses an OK of the dropped row"
echo nobody__nothing > $T/oks.unk
python3 -I $T/deal.py $IN $T/oks.unk $T/deal4 dataset-pathfix-b1 alibaba__AliSQL > $T/deal4.out 2>&1 && fail "deal took an unknown OK" || pass "deal refuses an unknown OK name"
python3 -I $T/deal.py $IN $T/oks.none $T/deal5 dataset-pathfix-b1 > $T/deal5.out 2>&1 && fail "deal ran without DROP" || pass "deal refuses to run without DROP (36 rows)"
# --- pf-seed on the deal-1 parts with a synthetic done-full/
DF=$T/done-full; mkdir -p $DF
python3 -I - $IN/seeds.tsv $DF <<'P'
import hashlib, json, sys
from pathlib import Path
lines = open(sys.argv[1]).read().splitlines(); head = lines[0].split("\t")
for x in lines[1:]:
    r = dict(zip(head, x.split("\t")))
    if r["resolved_sha"] != "S3":
        continue
    fake = hashlib.sha1(r["name"].encode()).hexdigest()
    d = Path(sys.argv[2]) / r["name"]; (d / "state").mkdir(parents=True)
    (d / "state" / "latest.json").write_text(json.dumps({"snapshot_sha": r["snapshot_sha"], "resolved_sha": fake, "branch": "main", "resolved_at": "2026-10-19T00:00:00+00:00"}) + "\n")
    (d / "ledger.rows.jsonl").write_text(json.dumps({"project": r["name"], "step": "resolve", "status": "ok"}) + "\n"
                                         + json.dumps({"project": r["name"], "step": "project", "state": "done", "checked_out_sha": fake}) + "\n")
P
for K in 1 2; do mkdir -p $T/part$K/ctp; cp $T/deal1/manifest.run.p$K.tsv $T/part$K/manifest.run.tsv; done
seed() { PF_INPUTS=$IN PF_PART_DIR=$T/part$1 PF_DONE_FULL=$DF python3 -I $T/pf-seed $1; }
seed 1 > $T/seed1.out && grep -q '^p1: 17 of 17 seeds OK' $T/seed1.out && pass "pf-seed p1: 17 of 17 (from seeds.tsv)" || { cat $T/seed1.out; fail "pf-seed p1"; }
seed 2 > $T/seed2.out && grep -q '^p2: 18 of 18 seeds OK' $T/seed2.out && pass "pf-seed p2: 18 of 18 (16 from done-full, 2 from seeds.tsv)" || { cat $T/seed2.out; fail "pf-seed p2"; }
python3 -I - $IN/seeds.tsv $T <<'P' && pass "every latest.json: resolved_sha = seed, snapshot_sha = seed, reused by ctp recorded_latest rules" || fail "latest.json content"
import hashlib, json, re, sys
from pathlib import Path
lines = open(sys.argv[1]).read().splitlines(); head = lines[0].split("\t"); T = Path(sys.argv[2])
n = 0
for x in lines[1:]:
    r = dict(zip(head, x.split("\t")))
    if r["name"] == "alibaba__AliSQL":
        assert not list(T.glob("part*/ctp/state/alibaba__AliSQL")), "AliSQL seeded"; continue
    f = [p for p in T.glob(f"part*/ctp/state/{r['name']}/latest.json")]
    assert len(f) == 1, (r["name"], f)
    j = json.loads(f[0].read_text())
    want = hashlib.sha1(r["name"].encode()).hexdigest() if r["resolved_sha"] == "S3" else r["resolved_sha"]
    assert j["resolved_sha"] == want and j["snapshot_sha"] == r["snapshot_sha"], r["name"]
    assert re.match(r"^[0-9a-f]{40}$", j["resolved_sha"]); n += 1
assert n == 35, n
P
seed 2 > $T/seed2b.out && grep -c 'in place' $T/seed2b.out | grep -q '^18$' && pass "pf-seed again: 18 seeds in place (idempotent)" || fail "pf-seed idempotent"
# negative: an existing latest.json with another commit is not overwritten
L=$T/part1/ctp/state/doocs__leetcode/latest.json; cp $L $T/leetcode.save
echo '{"resolved_sha": "0000000000000000000000000000000000000000"}' > $L
seed 1 > $T/seed1n.out; rc=$?
[ $rc = 1 ] && grep -q 'doocs__leetcode: SEED ERROR' $T/seed1n.out && grep -q '0000000000000000000000000000000000000000' $L && pass "pf-seed refuses another commit in an existing latest.json (exit 1, not overwritten)" || fail "pf-seed overwrite"
cp $T/leetcode.save $L
# negative: done-full latest.json with another snapshot
J=$DF/KSwordDEV__KSword/state/latest.json; cp $J $T/ksword.save; rm -f $T/part2/ctp/state/KSwordDEV__KSword/latest.json
python3 -I -c 'import json,sys; j=json.load(open(sys.argv[1])); j["snapshot_sha"]="1"*40; open(sys.argv[1],"w").write(json.dumps(j))' $J
seed 2 > $T/seed2n.out; [ $? = 1 ] && grep -q 'KSwordDEV__KSword: SEED ERROR: done-full latest.json snapshot_sha' $T/seed2n.out && pass "pf-seed refuses a done-full seed with another snapshot_sha" || fail "pf-seed snapshot check"
cp $T/ksword.save $J
# negative: the first-run checked_out_sha is not the resolved_sha
R=$DF/KSwordDEV__KSword/ledger.rows.jsonl; cp $R $T/ksword.rows.save; sed -i 's/"checked_out_sha": "[0-9a-f]*"/"checked_out_sha": "2222222222222222222222222222222222222222"/' $R
seed 2 > $T/seed2c.out; [ $? = 1 ] && grep -q 'KSwordDEV__KSword: SEED ERROR: first-run checked_out_sha' $T/seed2c.out && pass "pf-seed refuses when the first run checked out another commit" || fail "pf-seed checked_out check"
cp $T/ksword.rows.save $R
# negative: no done-full seed
mv $DF/KSwordDEV__KSword $DF/KSwordDEV__KSword.gone
seed 2 > $T/seed2m.out; [ $? = 1 ] && grep -q 'KSwordDEV__KSword: SEED ERROR: done-full/<name>/state/latest.json is not readable' $T/seed2m.out && pass "pf-seed refuses a missing done-full seed" || fail "pf-seed missing seed"
mv $DF/KSwordDEV__KSword.gone $DF/KSwordDEV__KSword
seed 2 > $T/seed2ok.out && pass "pf-seed p2 OK again after the restores" || { cat $T/seed2ok.out; fail "pf-seed restore"; }
[ $fails = 0 ] && echo "T1 ALL PASS" || { echo "T1: $fails FAILED"; exit 1; }
