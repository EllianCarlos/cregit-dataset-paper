#!/usr/bin/env bash
# R4-start-pf.sh (the path-fix instance, root, through scripts/ssm-run-pf.sh; after R1-setup-pf.sh,
# R2-gate-pf.sh (2 x CHECK OK) and R3-install-pf.sh): start the cregit path-fix rerun. Copy of
# ~/s3-work/dataset-x1k/scripts/w6/R4-start-b.sh with these changes:
#   1. inputs: s3://B/dataset-x1k/inputs-pathfix/ (U1-upload-pathfix.sh, ALL OK 2026-10-20) ->
#      /data/pathfix-inputs; its SHA256SUMS must be the staged one (sha256 c2c9ac76...) and every
#      file must match it. The x1k sidecar (the B sidecar) comes from
#      s3://B/dataset-x1k/inputs/project_meta.x1k.json. Each sidecar of sidecars.tsv is checked
#      with its sha256 in sidecar/<file>;
#   2. code check: each part's ctp clone is ca113e3 and clean, each cregit copy is at 14b8db4, the
#      ctp tests pass in p1's clone, each part's R2 gate Parquet is 14eb5d72 with 70 columns;
#   3. the deal is parts.tsv (no LPT, no HEAVY list). User decision 2026-10-20: NO AliSQL (it
#      loses 1 file of 458 bytes; a LIMITATIONS line records it), so DROP = alibaba__AliSQL and
#      part 3 (that held only AliSQL) goes away. p1 = 17 v1 rows, p2 = 18 x1k rows (35 rows); in
#      each part the longest rows (hours of parts.tsv) start first. Minus the rows with
#      dataset-x1k/done-pathfix/<name>/OK (a relaunch continues with the rest);
#   4. seeds: pf-seed K for each part (state/<name>/latest.json from seeds.tsv; S3 rows from
#      done-full/<name>/state/latest.json); a missing or wrong seed stops the start;
#   5. workers p1 4, p2 4 (WORKERS=<n> in the environment of this script sets both).
# Run id: /etc/dataset-pathfix/run (from R3-install-pf.sh). It refuses when live/<run>/START is in
# S3 already (a used run id): a relaunch takes a new NAME (dataset-pathfix-b1-r<n>). Writes
# /etc/dataset-pathfix/started and dataset-x1k/live/<run>/START and deal.tsv. Never on the
# instances of the refuse list.
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_LONG_A4}|${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_X1K_A}) echo "ABORT: $IID is on the refuse list"; exit 1 ;; esac
B=s3://${RUNNER_BUCKET}
E=/etc/dataset-pathfix; I=/data/pathfix-inputs
NCPU=$(nproc)
WORKERS=${WORKERS:-4}
WANT_PQ=14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
CREGIT_COMMIT=14b8db468e4f6565fab5692a1ab1c3066d12f371
WANT_SUMS=c2c9ac7695f68ba6e3679859192aadcbeee62463f4d6785472bd619f5272b58f
DROP="alibaba__AliSQL"
RUN=$(cat $E/run 2>/dev/null) || { echo "ABORT: no $E/run (run R3-install-pf.sh through scripts/ssm-run-pf.sh)"; exit 1; }
N=$(cat $E/nparts 2>/dev/null) || { echo "ABORT: no $E/nparts (run R3-install-pf.sh)"; exit 1; }
[ "$N" = 2 ] || { echo "ABORT: nparts '$N' is not 2"; exit 1; }
echo "== $(date -u +%FT%TZ) $IID R4-pf start, run $RUN, $N parts, $NCPU vCPU, $WORKERS workers per part"
aws s3 ls $B/dataset-x1k/live/$RUN/START >/dev/null 2>&1 && { echo "ABORT: live/$RUN/START is in S3: run id $RUN is used; launch with a new NAME"; exit 1; }
[ -f $E/started ] && { echo "ABORT: $E/started exists (this instance started already)"; exit 1; }
for K in $(seq 1 $N); do systemctl is-active -q pf@$K && { echo "ABORT: pf@$K runs already"; exit 1; }
  tail -1 $E/p$K.check 2>/dev/null | grep -q '^CHECK OK' || { echo "ABORT: p$K has no CHECK OK (run R2-gate-pf.sh)"; exit 1; }; done
[ -x /usr/local/bin/pf-run ] && [ -x /usr/local/bin/pf-seed ] || { echo "ABORT: run R3-install-pf.sh first"; exit 1; }
grep -q 'dataset-x1k/done-pathfix"' /usr/local/bin/pf-upload || { echo "ABORT: pf-upload does not write to done-pathfix/"; exit 1; }
grep -q 'live/$RUN/progress.txt' /usr/local/bin/pf-live || { echo "ABORT: pf-live is not the R3-install-pf.sh version"; exit 1; }
# 1. inputs
mkdir -p $I/sidecar
aws s3 cp $B/dataset-x1k/inputs-pathfix/ $I/ --recursive --only-show-errors || { echo "ABORT: inputs download"; exit 1; }
[ "$(sha256sum $I/SHA256SUMS | cut -d' ' -f1)" = $WANT_SUMS ] || { echo "ABORT: inputs-pathfix/SHA256SUMS is not the staged one ($WANT_SUMS)"; exit 1; }
(cd $I && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: inputs sha256"; exit 1; }
aws s3 cp $B/dataset-x1k/inputs/project_meta.x1k.json $I/sidecar/project_meta.x1k.json --only-show-errors || { echo "ABORT: x1k sidecar download"; exit 1; }
while IFS=$'\t' read -r part file sha path; do
  [ "$part" = part ] && continue
  [ "$(sha256sum $I/sidecar/$file 2>/dev/null | cut -d' ' -f1)" = "$sha" ] || { echo "ABORT: sidecar $file of part $part is not $sha"; exit 1; }
done < $I/sidecars.tsv
chown -R ec2-user:ec2-user $I; echo "inputs: $(head -1 $I/SOURCE); $(wc -l < $I/SHA256SUMS) files; sidecars ok: $(ls $I/sidecar | tr '\n' ' ')"
# 2. code check: the v1 code path (unpatched ca113e3, cregit 14b8db4, the R2 gate = 14eb5d72 with 70 columns)
for K in $(seq 1 $N); do C=/data$K/pf/ctp; D=/data$K/pf/cregit-ec2; G=/data$K/pf/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet
  h=$(sudo -u ec2-user git -C $C rev-parse --short HEAD); d=$(sudo -u ec2-user git -C $C status --porcelain --untracked-files=no)
  [ "$h" = ca113e3 ] && [ -z "$d" ] || { echo "ABORT: p$K ctp clone is $h, changes: $d"; exit 1; }
  [ "$(sudo -u ec2-user git -C $D rev-parse HEAD)" = $CREGIT_COMMIT ] || { echo "ABORT: p$K cregit copy is not at $CREGIT_COMMIT"; exit 1; }
  [ "$(sha256sum $G 2>/dev/null | cut -d' ' -f1)" = $WANT_PQ ] || { echo "ABORT: p$K gate Parquet is not 14eb5d72"; exit 1; }
  n=$(cd $C && sudo -u ec2-user .venv/bin/python -c 'import duckdb, sys; print(len(duckdb.connect().execute("describe select * from read_parquet(?)", [sys.argv[1]]).fetchall()))' $G)
  [ "$n" = 70 ] || { echo "ABORT: p$K gate Parquet has $n columns, not 70"; exit 1; }
  echo "p$K: ctp $h clean; cregit 14b8db4; gate Parquet 14eb5d72, $n columns (firm step in)"
done
t=$(cd /data1/pf/ctp && sudo -u ec2-user .venv/bin/python -m pytest -q -o addopts= -p no:cacheprovider 2>&1 | tail -1)
echo "ctp tests (p1 clone, ca113e3): $t"; echo "$t" | grep -q ' passed' && ! echo "$t" | grep -q -e failed -e error || { echo "ABORT: ctp tests"; exit 1; }
r="code: ctp ca113e3 unpatched (full pipeline), cregit 14b8db4, gate 14eb5d72 on both copies"
# 3. the deal: parts.tsv minus DROP minus done-pathfix/OK
aws s3 ls $B/dataset-x1k/done-pathfix/ --recursive > /tmp/pf-done.ls 2>/dev/null; rc=$?
# rc 1 with no output: the prefix is empty (first start)
[ $rc = 0 ] || { [ $rc = 1 ] && [ ! -s /tmp/pf-done.ls ]; } || { echo "ABORT: listing of done-pathfix/ (rc $rc)"; exit 1; }
awk '$4 ~ /^dataset-x1k\/done-pathfix\/[^\/]+\/OK$/ {split($4, a, "/"); print a[3]}' /tmp/pf-done.ls | sort -u > /tmp/pf-oks
echo "projects with done-pathfix/OK in S3: $(wc -l < /tmp/pf-oks)"
rm -rf /tmp/pf-deal; mkdir -p /tmp/pf-deal
python3 - $I /tmp/pf-oks /tmp/pf-deal "$RUN" $DROP <<'PY_DEAL' || { echo "ABORT: the deal"; exit 1; }
import sys
from pathlib import Path

inp, oks_file, out, run, drop = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), sys.argv[4], set(sys.argv[5:])
WANT = {1: 17, 2: 18}  # user decision 2026-10-20: 35 rows, no AliSQL (part 3 goes away)


def tsv(path):
    lines = [x for x in path.read_text().splitlines() if x.strip()]
    head = lines[0].split("\t")
    return [dict(zip(head, x.split("\t"))) for x in lines[1:]]


comments, man = [], {}
for line in (inp / "manifest.pathfix.tsv").read_text().splitlines():
    if line.startswith("#"):
        comments.append(line)
    elif line.strip():
        name = line.split("\t", 1)[0]
        assert name not in man, f"{name} twice in the manifest"
        man[name] = line
cols = next(c for c in comments if c.startswith("# Columns:"))
parts = tsv(inp / "parts.tsv")
seeds = {r["name"] for r in tsv(inp / "seeds.tsv")}
side = {r["part"] for r in tsv(inp / "sidecars.tsv")}
pnames = [r["name"] for r in parts]
assert len(pnames) == len(set(pnames)), "a name is twice in parts.tsv"
assert set(pnames) == set(man) == seeds, "parts.tsv, manifest.pathfix.tsv and seeds.tsv have other names"
assert drop and drop <= set(pnames), f"DROP rows not in parts.tsv: {sorted(drop - set(pnames))}"
done = {x.strip() for x in open(oks_file) if x.strip()}
assert not done - set(man), f"done-pathfix/OK names not in the manifest: {sorted(done - set(man))[:5]}"
assert not done & drop, f"a dropped row has done-pathfix/OK: {sorted(done & drop)}"
by_part = {}
for r in parts:
    by_part.setdefault(int(r["part"]), []).append(r)
gone = sorted(k for k, rows in by_part.items() if all(r["name"] in drop for r in rows))
keep = {k: [r for r in rows if r["name"] not in drop] for k, rows in by_part.items() if k not in gone}
assert sorted(keep) == sorted(WANT), f"parts after DROP: {sorted(keep)}, want {sorted(WANT)}"
for k, rows in keep.items():
    assert len(rows) == WANT[k], f"part {k}: {len(rows)} rows, want {WANT[k]}"
    assert str(k) in side, f"part {k} has no sidecar in sidecars.tsv"
    rows.sort(key=lambda r: (-float(r["hours"]), r["name"]))  # the longest rows start first
out.mkdir(parents=True, exist_ok=True)
n_run = n_skip = 0
with open(out / "deal.tsv", "w") as d:
    d.write("part\tseq\tproject\thours\tdone_pathfix\n")
    for k, rows in sorted(keep.items()):
        for j, r in enumerate(rows, 1):
            d.write(f"p{k}\t{j}\t{r['name']}\t{r['hours']}\t{int(r['name'] in done)}\n")
    for k in gone:
        for r in by_part[k]:
            d.write(f"dropped\t-\t{r['name']}\t{r['hours']}\t0\n")
for k, rows in sorted(keep.items()):
    run_rows = [r for r in rows if r["name"] not in done]
    n_run += len(run_rows); n_skip += len(rows) - len(run_rows)
    with open(out / f"manifest.run.p{k}.tsv", "w") as f:
        f.write(f"# path-fix rerun {run}: part p{k} of parts.tsv (minus {', '.join(sorted(drop))}; minus done-pathfix/OK); "
                f"longest rows first.\n{cols}\n")
        for r in run_rows:
            f.write(man[r["name"]] + "\n")
    print(f"p{k}: {len(rows)} rows, {len(rows) - len(run_rows)} with done-pathfix/OK, {len(run_rows)} to run, "
          f"{sum(float(r['hours']) for r in run_rows):.2f} serial h (first run), first {run_rows[0]['name'] if run_rows else '-'}")
print(f"manifest rows {len(man)}; dropped {len(drop)} ({', '.join(sorted(drop))}; part {', '.join(map(str, gone))} goes away); "
      f"dealt {sum(len(v) for v in keep.values())} to {len(keep)} parts; {n_run} to run, {n_skip} with done-pathfix/OK")
PY_DEAL
for K in $(seq 1 $N); do R=/data$K/pf/manifest.run.tsv
  mv -f /tmp/pf-deal/manifest.run.p$K.tsv $R; chown ec2-user: $R
  echo "p$K: $(grep -c -v -e '^#' -e '^[[:space:]]*$' $R) rows to run"
done
cp /tmp/pf-deal/deal.tsv $E/deal.tsv; chmod 644 $E/deal.tsv
# 4. seeds (pf-run checks them again at its start)
for K in $(seq 1 $N); do
  sudo -u ec2-user /usr/local/bin/pf-seed $K | tail -40 || { echo "ABORT: p$K seeds (see the SEED ERROR lines)"; exit 1; }
done
# 5. start
for K in $(seq 1 $N); do echo $WORKERS > $E/workers.p$K; done
echo "started $(date -u +%FT%TZ) on $IID, run $RUN, full pipeline, $NCPU vCPU, $WORKERS workers per part" > $E/started
systemctl daemon-reload
systemctl enable --now pf-watch.service >/dev/null 2>&1; systemctl start pf-upload.timer pf-live.timer pf-finalize.timer
for K in $(seq 1 $N); do systemctl reset-failed pf@$K 2>/dev/null; systemctl start pf@$K; done
{ cat $E/started; for K in $(seq 1 $N); do echo "p$K: $(grep -c -v -e '^#' -e '^[[:space:]]*$' /data$K/pf/manifest.run.tsv) rows"; done; echo "$t"; echo "$r"; } > /tmp/pf-START
aws s3 cp /tmp/pf-START $B/dataset-x1k/live/$RUN/START --only-show-errors
aws s3 cp $E/deal.tsv $B/dataset-x1k/live/$RUN/deal.tsv --only-show-errors
sleep 60
for K in $(seq 1 $N); do echo "p$K: $(systemctl is-active pf@$K) $(tail -1 /data$K/pf/logs/run.log | cut -c1-200)"; done
echo "R4-pf done $(date -u +%FT%TZ)"
