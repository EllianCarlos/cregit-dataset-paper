#!/usr/bin/env bash
# R3-install-pf.sh (the path-fix instance, root, through scripts/ssm-run-pf.sh; idempotent; starts
# nothing): the run scripts and units of the cregit path-fix rerun. Copy of
# ~/s3-work/dataset-x1k/scripts/w6/R3-install-b.sh (machine B of x1k, full pipeline) with these
# changes:
#   - run id PF_RUN (from ssm-run-pf.sh) = the NAME of the L1-launch-pf.sh instance:
#     dataset-pathfix-b1, after a reclaim dataset-pathfix-b1-r<n>. Live files go to
#     s3://B/dataset-x1k/live/<run>/, final files to s3://B/dataset-x1k/final/<run>/ (new keys: no
#     x1k run has a run id that starts with dataset-pathfix);
#   - 2 parts: p1 = the 17 v1 rows, p2 = the 18 x1k rows, on /data1/pf and /data2/pf; config in
#     /etc/dataset-pathfix/; units pf@K, pf-upload, pf-live, pf-watch, pf-finalize;
#   - inputs /data/pathfix-inputs (R4-start-pf.sh fetches them): manifest.run.tsv per part,
#     seeds.tsv, sidecars.tsv, sidecar/<file>;
#   - pf-run K: --project-meta = the sidecar of part K in sidecars.tsv (sha256 checked); the flags of
#     the v1 fed parts as B (--blame-jobs 4; part 3 with --blame-jobs 32 is not made: no AliSQL);
#     before the census it runs pf-seed K and stops (exit 3) if a seed is missing or does not match;
#   - pf-seed K: writes ctp state/<name>/latest.json for each row of the part's manifest.run.tsv, so
#     --latest REUSES the commit of the first run (ctp ca113e3 resolve_latest) and the ledger keeps
#     snapshot_sha = the manifest commit. Rows with resolved_sha "S3" in seeds.tsv (x1k rows with a
#     Parquet) read dataset-x1k/done-full/<name>/state/latest.json and ledger.rows.jsonl with the
#     role of the machine; the seed must have the seeds.tsv snapshot_sha, a 40-hex resolved_sha,
#     and the final "project" row of the first run must have checked_out_sha = resolved_sha. Other
#     rows take resolved_sha, snapshot_sha and branch from seeds.tsv. An existing latest.json with
#     another resolved_sha is an error (never overwritten);
#   - pf-upload: the done set is s3://B/dataset-x1k/done-pathfix/<name>/ (done-full/ and done/ are
#     only read, never written); it never writes into a done-pathfix/<name>/ that has OK.
#   - pf-finalize: as B: copy ledgers and logs to final/<run>/pK/, size check, final/<run>/DONE;
#     power-off only after final/<run>/DONE is in S3 with the local size, every part ended with
#     "census finished", no /home/ec2-user/NO_SHUTDOWN, no /run/pf-hold and up >= 1 h (shutdown
#     terminates the spot instance). A part without "census finished" -> live/<run>/ALERT, no
#     shutdown.
# Code path: the UNPATCHED ctp ca113e3, cregit 14b8db4, flags --retries 3 --skip-html --latest
# --tokenizer-worker --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300.
set -euo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
case $IID in ${RUNNER_EC2_BIG}|${RUNNER_EC2_X1K_LONG_A4}|${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_X1K_A}) echo "ABORT: $IID is on the refuse list"; exit 1 ;; esac
RUN=${PF_RUN:-}
[[ $RUN =~ ^dataset-pathfix-b1(-r[0-9]+)?$ ]] || { echo "ABORT: PF_RUN '$RUN' is not dataset-pathfix-b1[-rN]; run R3-install-pf.sh through scripts/ssm-run-pf.sh"; exit 1; }
E=/etc/dataset-pathfix
mkdir -p $E
if [ -f $E/run ] && [ "$(cat $E/run)" != "$RUN" ]; then
  echo "ABORT: this instance has the run id $(cat $E/run), not $RUN"; exit 1
fi
echo "$RUN" > $E/run; echo 2 > $E/nparts; chmod 644 $E/run $E/nparts
echo "run id $RUN: live files to dataset-x1k/live/$RUN/, final files to dataset-x1k/final/$RUN/, done set dataset-x1k/done-pathfix/"
cat > /usr/local/bin/pf-run.new <<'EOF_pf_run'
#!/usr/bin/env bash
# pf-run K (pf@K.service, ec2-user): the ctp census of path-fix part pK. Stop after the running
# projects: touch /dataK/pf/ctp/STOP (pf-watch does it on a spot notice).
set -euo pipefail
K=${1:?part}; P=/data$K/pf; I=/data/pathfix-inputs; M=$P/manifest.run.tsv
W=$(cat /etc/dataset-pathfix/workers.p$K 2>/dev/null || echo 4)
export CTP_CONFIG=/etc/dataset-pathfix/p$K.cfg
cd $P/ctp
# the v1 code path: ctp ca113e3 without any patch
[ "$(git rev-parse --short HEAD)" = ca113e3 ] && [ -z "$(git status --porcelain --untracked-files=no)" ] \
  || { echo "ctp of p$K is not the clean ca113e3"; exit 2; }
SC_FILE=; SC_SHA=
read -r SC_FILE SC_SHA < <(awk -F'\t' -v k=$K 'NR>1 && $1==k {print $2, $3}' $I/sidecars.tsv) || true
[ -n "${SC_FILE:-}" ] && [ "$(sha256sum "$I/sidecar/$SC_FILE" | cut -d' ' -f1)" = "$SC_SHA" ] \
  || { echo "p$K: sidecar of sidecars.tsv missing or sha256 differs"; exit 2; }
/usr/local/bin/pf-seed $K || { echo "p$K: the seeds are not correct; no start"; exit 3; }
echo "=== $(date -u +%FT%TZ) path-fix part p$K start on $(cat /sys/devices/virtual/dmi/id/board_asset_tag) run $(cat /etc/dataset-pathfix/run) (cregit $(git -C $P/cregit-ec2 rev-parse --short HEAD), ctp $(git rev-parse --short HEAD) full pipeline, $(grep -c -v -e '^#' -e '^[[:space:]]*$' $M) projects, $W workers, sidecar $SC_FILE)"
exec .venv/bin/python ctp.py census --manifest "$M" --project-meta "$I/sidecar/$SC_FILE" \
    --workers "$W" --retries 3 --skip-html --latest --tokenizer-worker \
    --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 300
EOF_pf_run
cat > /usr/local/bin/pf-seed.new <<'EOF_pf_seed'
#!/usr/bin/env python3
"""pf-seed K (ec2-user; pf-run and R4-start-pf.sh call it): the --latest seeds of path-fix part pK.

For each row of /dataK/pf/manifest.run.tsv it writes ctp state/<name>/latest.json (the file
ctp ca113e3 resolve_latest() reuses), so the rerun checks out the commit of the first run.
seeds.tsv columns: name, resolved_sha, snapshot_sha, branch, source. resolved_sha "S3": the
seed is dataset-x1k/done-full/<name>/state/latest.json (read with the role of the machine); its
snapshot_sha must be that of seeds.tsv, and the final "project" row of done-full/<name>/
ledger.rows.jsonl must have checked_out_sha = its resolved_sha. Every seed: snapshot_sha = the
manifest commit, resolved_sha 40 hex. An existing latest.json with the same resolved_sha stays;
with another one it is an error (never overwritten). Exit 0 only if every row has its seed.
Environment (tests only): PF_INPUTS, PF_PART_DIR, PF_DONE_FULL (a local folder instead of S3).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")
K = sys.argv[1]
INP = Path(os.environ.get("PF_INPUTS", "/data/pathfix-inputs"))
PART = Path(os.environ.get("PF_PART_DIR", f"/data{K}/pf"))
DONE_FULL = os.environ.get("PF_DONE_FULL", "s3://${RUNNER_BUCKET}/dataset-x1k/done-full")


def fetch(name, rel, tmp):
    """done-full/<name>/<rel> to tmp; None if it is not there."""
    dst = Path(tmp) / rel.replace("/", "_")
    if DONE_FULL.startswith("s3://"):
        r = subprocess.run(["aws", "s3", "cp", f"{DONE_FULL}/{name}/{rel}", str(dst), "--only-show-errors"],
                           capture_output=True, text=True)
        return dst if r.returncode == 0 and dst.is_file() else None
    src = Path(DONE_FULL) / name / rel
    if not src.is_file():
        return None
    dst.write_bytes(src.read_bytes())
    return dst


def final_checked_out(ledger_rows):
    sha = None
    for line in ledger_rows.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("step") == "project" and r.get("state") in ("done", "done-dirty"):
            sha = r.get("checked_out_sha")
    return sha


def seed_for(name, row, seed, tmp):
    url, commit = row[1], row[5]
    if seed["snapshot_sha"] != commit:
        raise ValueError(f"seeds.tsv snapshot_sha {seed['snapshot_sha'][:12]} is not the manifest commit {commit[:12]}")
    if seed["resolved_sha"] == "S3":
        f = fetch(name, "state/latest.json", tmp)
        if f is None:
            raise ValueError("done-full/<name>/state/latest.json is not readable")
        rec = json.loads(f.read_text())
        if rec.get("snapshot_sha") != seed["snapshot_sha"]:
            raise ValueError(f"done-full latest.json snapshot_sha {str(rec.get('snapshot_sha'))[:12]} is not {seed['snapshot_sha'][:12]}")
        if not SHA.match(rec.get("resolved_sha", "")):
            raise ValueError("done-full latest.json has no 40-hex resolved_sha")
        if rec.get("url") and rec["url"] != url:
            raise ValueError(f"done-full latest.json url {rec['url']} is not the manifest url {url}")
        lr = fetch(name, "ledger.rows.jsonl", tmp)
        if lr is None:
            raise ValueError("done-full/<name>/ledger.rows.jsonl is not readable")
        got = final_checked_out(lr)
        if got != rec["resolved_sha"]:
            raise ValueError(f"first-run checked_out_sha {str(got)[:12]} is not the resolved_sha {rec['resolved_sha'][:12]}")
        rec["seeded"] = f"pathfix pf-seed {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} from done-full/{name}/state/latest.json"
        return rec
    if not SHA.match(seed["resolved_sha"]):
        raise ValueError(f"seeds.tsv resolved_sha {seed['resolved_sha']!r} is not 40 hex")
    return {"url": url, "snapshot_sha": seed["snapshot_sha"], "resolved_sha": seed["resolved_sha"],
            "branch": seed["branch"], "resolved_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
            "seeded": f"pathfix pf-seed from seeds.tsv ({seed['source']})"}


def main():
    lines = (INP / "seeds.tsv").read_text().splitlines()
    head = lines[0].split("\t")
    seeds = {}
    for x in lines[1:]:
        if x.strip():
            r = dict(zip(head, x.split("\t")))
            seeds[r["name"]] = r
    rows = [x.split("\t") for x in (PART / "manifest.run.tsv").read_text().splitlines()
            if x.strip() and not x.startswith("#")]
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for row in rows:
            name = row[0]
            path = PART / "ctp" / "state" / name / "latest.json"
            try:
                if name not in seeds:
                    raise ValueError("no row in seeds.tsv")
                want = seed_for(name, row, seeds[name], tmp)
                if path.exists():
                    have = json.loads(path.read_text()).get("resolved_sha", "")
                    if have != want["resolved_sha"]:
                        raise ValueError(f"{path} has resolved_sha {have[:12]}, the seed is {want['resolved_sha'][:12]}; not overwritten")
                    print(f"p{K} {name}: seed {have[:12]} in place")
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                t = path.with_suffix(".tmp")
                t.write_text(json.dumps(want) + "\n")
                t.replace(path)
                print(f"p{K} {name}: seed {want['resolved_sha'][:12]} written (snapshot {want['snapshot_sha'][:12]})")
            except (ValueError, OSError, KeyError, IndexError) as x:
                bad += 1
                print(f"p{K} {name}: SEED ERROR: {x}")
    print(f"p{K}: {len(rows) - bad} of {len(rows)} seeds OK")
    return 1 if bad or not rows else 0


if __name__ == "__main__":
    sys.exit(main())
EOF_pf_seed
cat > /usr/local/bin/pf-upload.new <<'EOF_pf_upload'
#!/usr/bin/env python3
"""pf-upload (pf-upload.timer, ec2-user): copy each finished path-fix project to S3.

Copy of x1k-upload (R3-install-b.sh). A project is finished when its last final ledger row
("project") says done or done-dirty and its .validated stamp exists. For each one not yet uploaded
it copies out/<name>/<name>-dataset.parquet, out/<name>/<name>.validated, out/<name>/<name>-persons.db
(if it exists), ctp state/<name>/*.json and state/<name>/logs/* (regular files) and the ledger rows
of the project (ledger.rows.jsonl) to s3://BUCKET/dataset-x1k/done-pathfix/<name>/, lists the prefix
back and compares every key and size, then writes done-pathfix/<name>/OK (time, instance, part,
files, sizes, Parquet sha256) and a local marker /dataK/pf/uploaded/<name>. It never writes into a
done-pathfix/<name>/ that has OK.
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
DEST = f"{B}/dataset-x1k/done-pathfix"  # path-fix rerun: own done set; done-full/ and done/ stay untouched
NPARTS = int(Path("/etc/dataset-pathfix/nparts").read_text().strip())


def finished(ctp):
    final, rows = {}, {}
    try:
        with (ctp / "ledger.jsonl").open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                p = r.get("project")
                if p:
                    rows.setdefault(p, []).append(line)
                if r.get("step") == "project" and p:
                    final[p] = r.get("state")
    except OSError:
        return [], {}
    return [p for p, s in final.items() if s in ("done", "done-dirty")], rows


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def upload(name, k, part, rows):
    ctp, out = part / "ctp", part / "out"
    pq = out / name / f"{name}-dataset.parquet"
    stamp = out / name / f"{name}.validated"
    if not (pq.is_file() and stamp.is_file()):
        return f"p{k} {name}: Parquet or stamp missing, later"
    have = subprocess.run(["aws", "s3", "ls", f"{DEST}/{name}/OK"], capture_output=True, text=True)
    if have.returncode == 0 and have.stdout.strip().endswith(" OK"):
        (part / "uploaded").mkdir(parents=True, exist_ok=True)
        (part / "uploaded" / name).write_text("done-pathfix/OK was in S3 before this run; nothing uploaded\n")
        return f"p{k} {name}: done-pathfix/{name}/OK exists already, not overwritten"
    stage = part / "upload-stage"  # same filesystem as out/, so os.link works
    stage.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}.", dir=stage))
    try:
        for f in (pq, stamp):
            os.link(f, tmp / f.name)
        persons = out / name / f"{name}-persons.db"
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
        (tmp / "ledger.rows.jsonl").write_text("".join(rows.get(name, [])))
        local = {str(p.relative_to(tmp)): p.stat().st_size for p in tmp.rglob("*") if p.is_file()}
        subprocess.run(["aws", "s3", "cp", f"{tmp}/", f"{DEST}/{name}/", "--recursive",
                        "--only-show-errors"], check=True)
        ls = subprocess.run(["aws", "s3", "ls", f"{DEST}/{name}/", "--recursive"], check=True,
                            capture_output=True, text=True).stdout
        prefix = DEST.split("/", 3)[3] + f"/{name}/"
        remote = {}
        for line in ls.splitlines():
            c = line.split(None, 3)
            if len(c) == 4 and c[3].startswith(prefix):
                remote[c[3][len(prefix):]] = int(c[2])
        bad = [key for key, v in local.items() if remote.get(key) != v]
        if bad:
            return f"p{k} {name}: size check FAILED for {bad[:5]}, will retry"
        ok = tmp / "OK"
        instance = Path("/sys/devices/virtual/dmi/id/board_asset_tag").read_text().strip()
        ok.write_text(f"uploaded {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} from {instance} part p{k}\n"
                      f"parquet_sha256 {sha256(pq)}\n"
                      + "".join(f"{v}\t{key}\n" for key, v in sorted(local.items())))
        subprocess.run(["aws", "s3", "cp", str(ok), f"{DEST}/{name}/OK", "--only-show-errors"], check=True)
        (part / "uploaded").mkdir(parents=True, exist_ok=True)
        (part / "uploaded" / name).write_text(ok.read_text())
        return f"p{k} {name}: uploaded {len(local)} files, sizes equal, OK written"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for k in range(1, NPARTS + 1):
        part = Path(f"/data{k}/pf")
        names, rows = finished(part / "ctp")
        for name in names:
            if (part / "uploaded" / name).exists():
                continue
            try:
                print(time.strftime("%FT%TZ", time.gmtime()), upload(name, k, part, rows), flush=True)
            except (subprocess.CalledProcessError, OSError) as x:
                print(time.strftime("%FT%TZ", time.gmtime()), f"p{k} {name}: upload error {x}, will retry", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
EOF_pf_upload
cat > /usr/local/bin/pf-live.new <<'EOF_pf_live'
#!/usr/bin/env bash
# pf-live (pf-live.timer, ec2-user): the run state to s3://B/dataset-x1k/live/<run>/progress.txt.
set -uo pipefail
B=s3://${RUNNER_BUCKET}
RUN=$(cat /etc/dataset-pathfix/run); N=$(cat /etc/dataset-pathfix/nparts)
T=$(mktemp)
{
  echo "path-fix live run $RUN $(date -u +%FT%TZ) on $(cat /sys/devices/virtual/dmi/id/board_asset_tag), up $(awk '{printf "%.1f h", $1/3600}' /proc/uptime)"
  tot=0; done_=0
  for K in $(seq 1 $N); do P=/data$K/pf; M=$P/manifest.run.tsv
    n=$(grep -c -v -e '^#' -e '^[[:space:]]*$' $M 2>/dev/null); n=${n:-0}; u=$(ls $P/uploaded 2>/dev/null | wc -l)
    tot=$((tot + n)); done_=$((done_ + u))
    echo "--- p$K: unit $(systemctl is-active pf@$K) | uploaded $u of $n | $(df -h --output=avail /data$K | tail -1 | tr -d ' ') free"
    (cd $P/ctp && CTP_CONFIG=/etc/dataset-pathfix/p$K.cfg .venv/bin/python ctp.py progress --manifest $M --last 2 2>&1 | head -6)
    tail -1 $P/logs/run.log 2>/dev/null | cut -c1-200
  done
  echo "=== all parts: uploaded $done_ of $tot"
  free -g | sed -n 2p; uptime
  [ -e /run/pf-spot-interrupted ] && echo "SPOT INTERRUPTION: $(cat /run/pf-spot-interrupted)"
} > $T 2>&1
aws s3 cp $T $B/dataset-x1k/live/$RUN/progress.txt --only-show-errors
rm -f $T
EOF_pf_live
cat > /usr/local/bin/pf-watch.new <<'EOF_pf_watch'
#!/usr/bin/env bash
# pf-watch (pf-watch.service, root): poll IMDSv2 spot/instance-action every 5 s, as census-fed-watch.
# On a notice: /run/pf-spot-interrupted, STOP in every part's ctp clone (no new project starts),
# INTERRUPTED and each part's ledger to s3://B/dataset-x1k/live/<run>/, one pf-upload. EC2 terminates
# the instance about 2 min later; the relaunch steps are in ~/s3-work/dataset-pathfix/README.md.
set -uo pipefail
B=s3://${RUNNER_BUCKET}
IMDS=http://169.254.169.254/latest
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
RUN=$(cat /etc/dataset-pathfix/run); N=$(cat /etc/dataset-pathfix/nparts)
echo "$(date -u +%FT%TZ) watching $IMDS/meta-data/spot/instance-action every 5 s"
while :; do
  tok=$(curl -s -m 2 -X PUT "$IMDS/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
  if [ -n "$tok" ]; then
    code=$(curl -s -m 2 -o /run/pf-instance-action -w '%{http_code}' -H "X-aws-ec2-metadata-token: $tok" "$IMDS/meta-data/spot/instance-action")
    if [ "$code" = 200 ]; then
      echo "$(date -u +%FT%TZ) $(cat /run/pf-instance-action)" > /run/pf-spot-interrupted
      T=$(mktemp -d)
      for K in $(seq 1 $N); do touch /data$K/pf/ctp/STOP; chown ec2-user: /data$K/pf/ctp/STOP
        [ -f /data$K/pf/ctp/ledger.jsonl ] && cp /data$K/pf/ctp/ledger.jsonl $T/ledger.p$K.jsonl; done
      { echo "spot interruption notice seen $(date -u +%FT%TZ) on $IID (run $RUN)"; cat /run/pf-instance-action; echo
        for K in $(seq 1 $N); do echo "p$K uploaded $(ls /data$K/pf/uploaded | wc -l)"; done; } > $T/INTERRUPTED
      aws s3 cp $T/ $B/dataset-x1k/live/$RUN/ --recursive --only-show-errors
      sudo -u ec2-user /usr/local/bin/pf-upload
      echo "real notice handled; idle until termination"; exec sleep infinity
    fi
  fi
  sleep 5
done
EOF_pf_watch
cat > /usr/local/bin/pf-finalize.new <<'EOF_pf_finalize'
#!/usr/bin/env bash
# pf-finalize (root; pf-finalize.service, after each part ends and every 15 min): see R3-install-pf.sh.
set -uo pipefail
B=s3://${RUNNER_BUCKET}
E=/etc/dataset-pathfix
[ -f $E/started ] || exit 0
RUN=$(cat $E/run) || exit 1
N=$(cat $E/nparts) || exit 1
F=$B/dataset-x1k/final/$RUN
[ -e /run/pf-spot-interrupted ] && exit 0
for K in $(seq 1 $N); do systemctl is-active -q pf@$K && exit 0; done
[ -f $E/final-DONE ] && exit 0
echo "$(date -u +%FT%TZ) all $N parts inactive: final upload"
sudo -u ec2-user /usr/local/bin/pf-upload
clean=1; T=$(mktemp -d)
for K in $(seq 1 $N); do P=/data$K/pf; C=$P/ctp; mkdir -p $T/p$K
  grep -q 'census finished rc=' $P/logs/run.log 2>/dev/null || clean=0
  for f in ledger.jsonl runs.log metrics.tsv resources.tsv; do [ -f $C/$f ] && cp $C/$f $T/p$K/; done
  cp $P/logs/run.log $P/manifest.run.tsv $T/p$K/ 2>/dev/null
  ls $P/uploaded > $T/p$K/uploaded.txt
  # state of the projects without an upload (failed, deferred or not started)
  (cd $C/state 2>/dev/null && ls | grep -v -x -F -f $T/p$K/uploaded.txt | tar -czf $T/p$K/state-not-uploaded.tar.gz -T - 2>/dev/null)
done
aws s3 cp $T/ $F/ --recursive --only-show-errors
ok=1
for f in $(cd $T && find . -type f | sed 's|^\./||'); do
  s=$(aws s3 ls $F/$f | awk '{print $3}')
  [ "$s" = "$(stat -c %s $T/$f)" ] || { ok=0; echo "size check failed: $f"; }
done
if [ $ok = 1 ] && [ $clean = 1 ]; then
  { echo "path-fix final run $RUN $(date -u +%FT%TZ) on $(cat /sys/devices/virtual/dmi/id/board_asset_tag)"
    for K in $(seq 1 $N); do echo "p$K: uploaded $(wc -l < $T/p$K/uploaded.txt) of $(grep -c -v -e '^#' -e '^[[:space:]]*$' $T/p$K/manifest.run.tsv); $(grep 'census finished rc=' $T/p$K/run.log | tail -1 | cut -c1-200)"; done
  } > $T/DONE
  aws s3 cp $T/DONE $F/DONE --only-show-errors
  cat $T/DONE
  up=$(awk '{print int($1)}' /proc/uptime)
  # Power off only when final/<run>/DONE is in S3 with the local size; else no final-DONE, so the
  # next timer run (15 min) does the final copy again.
  if [ "$(aws s3 ls $F/DONE | awk '{print $3}')" != "$(stat -c %s $T/DONE)" ]; then
    echo "final/$RUN/DONE is not in S3 with the correct size: no shutdown, retry at the next timer run"
  elif ! cp $T/DONE $E/final-DONE; then
    echo "cannot write $E/final-DONE: no shutdown"
  elif [ -e /home/ec2-user/NO_SHUTDOWN ] || [ -e /run/pf-hold ] || [ "$up" -lt 3600 ]; then
    echo "no shutdown (NO_SHUTDOWN, /run/pf-hold or up < 1 h)"
  else
    echo "shutdown in 2 min (the instance terminates)"; shutdown -h +2
  fi
else
  { echo "path-fix ALERT run $RUN $(date -u +%FT%TZ): all parts inactive, clean=$clean (a part without 'census finished'), size check ok=$ok; no shutdown"; } > $T/ALERT
  aws s3 cp $T/ALERT $B/dataset-x1k/live/$RUN/ALERT --only-show-errors; cat $T/ALERT
fi
EOF_pf_finalize
for f in pf-run pf-seed pf-upload pf-live pf-watch pf-finalize; do chmod 755 /usr/local/bin/$f.new; mv -f /usr/local/bin/$f.new /usr/local/bin/$f; done
cat > /etc/systemd/system/pf@.service <<'EOF_u1'
[Unit]
Description=cregit path-fix rerun part p%i (ctp census, full pipeline, own XFS /data%i)
Wants=network-online.target
After=network-online.target nix-daemon.service
RequiresMountsFor=/data%i
OnSuccess=pf-finalize.service
OnFailure=pf-finalize.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/data%i/pf/ctp
ExecStart=/usr/local/bin/pf-run %i
StandardOutput=append:/data%i/pf/logs/run.log
StandardError=append:/data%i/pf/logs/run.log
Restart=no
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStopSec=300
EOF_u1
cat > /etc/systemd/system/pf-finalize.service <<'EOF_u2'
[Unit]
Description=path-fix rerun: final copy to S3 and power-off when every part has ended

[Service]
Type=oneshot
ExecStart=/usr/local/bin/pf-finalize
StandardOutput=append:/data/logs/pf-finalize.log
StandardError=append:/data/logs/pf-finalize.log
TimeoutStartSec=3600
EOF_u2
cat > /etc/systemd/system/pf-finalize.timer <<'EOF_u3'
[Unit]
Description=path-fix rerun: finalize check every 15 min

[Timer]
OnActiveSec=15min
OnUnitActiveSec=15min
EOF_u3
cat > /etc/systemd/system/pf-upload.service <<'EOF_u4'
[Unit]
Description=path-fix rerun: copy finished projects to S3 dataset-x1k/done-pathfix/

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/pf-upload
StandardOutput=append:/data/logs/pf-upload.log
StandardError=append:/data/logs/pf-upload.log
TimeoutStartSec=3600
EOF_u4
cat > /etc/systemd/system/pf-upload.timer <<'EOF_u5'
[Unit]
Description=path-fix rerun: copy finished projects to S3 every 2 min

[Timer]
OnActiveSec=2min
OnUnitActiveSec=2min
AccuracySec=10s
EOF_u5
cat > /etc/systemd/system/pf-live.service <<'EOF_u6'
[Unit]
Description=path-fix rerun: live status to S3

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/pf-live
TimeoutStartSec=600
EOF_u6
cat > /etc/systemd/system/pf-live.timer <<'EOF_u7'
[Unit]
Description=path-fix rerun: live status to S3 every 10 min

[Timer]
OnActiveSec=1min
OnUnitActiveSec=10min
AccuracySec=30s
EOF_u7
cat > /etc/systemd/system/pf-watch.service <<'EOF_u8'
[Unit]
Description=path-fix rerun: watch for a spot interruption notice (IMDSv2)
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/pf-watch
StandardOutput=append:/data/logs/pf-watch.log
StandardError=append:/data/logs/pf-watch.log
Restart=always
RestartSec=5
EOF_u8
mkdir -p /data/logs; chown ec2-user: /data/logs
systemctl daemon-reload
bash -n /usr/local/bin/pf-run && bash -n /usr/local/bin/pf-live && bash -n /usr/local/bin/pf-watch && bash -n /usr/local/bin/pf-finalize \
  && python3 -c 'import ast, sys; [ast.parse(open(f).read()) for f in sys.argv[1:]]' /usr/local/bin/pf-upload /usr/local/bin/pf-seed \
  && echo "R3-pf installed (run $RUN): $(ls /usr/local/bin | grep -c '^pf-') scripts, units: $(ls /etc/systemd/system | grep '^pf' | tr '\n' ' ')"
