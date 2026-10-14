set -euo pipefail
cat > /usr/local/bin/census-steps.new <<'EOF_census-steps'
#!/usr/bin/env python3
"""census-steps CTP_DIR MANIFEST [--highlight REGEX]: the cregit step of every running project.

Read-only: it reads CTP_DIR/ledger.jsonl and CTP_DIR/state/<name>/logs/*.log and prints a table.
A project is running when its last ledger row in the newest census run is not the final
"project" row. For a project in the ctp "pipeline" phase the step is the last "Step N — name"
header in its newest pipeline log. The runner prints no time on a header, so the step start is
computed: the pipeline start (the ledger "pipeline started" row of that attempt) plus the
"completed in Ns" of every earlier step in the same log. That is exact to a second or two.
--counts prints only "RUNNING NOT_STARTED". Projects whose name matches --highlight (default LineageOS) are always listed first, with
their state even when they are not running (queued, done, failed).
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

HEADER = re.compile(r"^\s*Step (\d+) — (.+?)\s*$")
DONE = re.compile(r"✓ completed in (\d+)s")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def parse_utc(text):
    try:
        t = dt.datetime.fromisoformat(text)
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def fmt_age(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"


def manifest_names(path):
    names = []
    for line in Path(path).read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            names.append(line.split("\t")[0])
    return names


def ledger_rows(ctp):
    rows = []
    try:
        with (ctp / "ledger.jsonl").open() as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return rows


def newest_log(state, name, phase):
    logs = sorted((state / name / "logs").glob(f"{phase}-2*.log"))
    return logs[-1] if logs else None


def last_line(path):
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 8192))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return ""
    lines = [ANSI.sub("", l).strip() for l in tail.replace("\r", "\n").splitlines()]
    lines = [l for l in lines if l and not set(l) <= set("═█")]
    return lines[-1][:150] if lines else ""


def pipeline_step(log, base):
    """(step, name, start) of the last header in log; start from base plus completed steps."""
    step = name = None
    elapsed = 0
    start = None
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None, None
    for line in text.splitlines():
        m = HEADER.match(line)
        if m:
            step, name = int(m.group(1)), m.group(2)
            start = base + dt.timedelta(seconds=elapsed) if base else None
            continue
        d = DONE.search(line)
        if d:
            elapsed += int(d.group(1))
    return step, name, start


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ctp")
    ap.add_argument("manifest")
    ap.add_argument("--highlight", default="LineageOS")
    ap.add_argument("--counts", action="store_true",
                    help='print only "RUNNING NOT_STARTED" for the newest run (for census-batch3L-wait)')
    args = ap.parse_args()
    ctp = Path(args.ctp)
    state = ctp / "state"
    now = dt.datetime.now(dt.timezone.utc)
    names = manifest_names(args.manifest)
    rows = ledger_rows(ctp)
    runs = [r for r in rows if r.get("step") == "run-start" and r.get("command", "census") == "census"]
    run_id = runs[-1].get("run_id") if runs else (rows[-1].get("run_id") if rows else None)
    cur = [r for r in rows if r.get("run_id") == run_id and r.get("project")]
    last, pipe_start, finals, started = {}, {}, {}, set()
    for r in cur:
        p = r["project"]
        last[p] = r
        started.add(p)
        if r.get("step") == "pipeline" and r.get("status") == "started":
            pipe_start[p] = parse_utc(r.get("start_utc"))
        if r.get("step") == "project":
            finals[p] = r.get("state")
    # Final state over all runs, for projects that this run skipped (no ledger row).
    ever = {}
    for r in rows:
        if r.get("step") == "project" and r.get("project"):
            ever[r["project"]] = r.get("state")
    running = [n for n in names if n in last and last[n].get("step") != "project"]
    pending = [n for n in names if n not in started and ever.get(n) not in ("done", "done-dirty", "skipped")]
    if args.counts:
        print(len(running), len(pending))
        return 0
    print(f"as of {now:%Y-%m-%dT%H:%M:%SZ}  run {run_id}  running {len(running)}  "
          f"not started {len(pending)}  manifest {len(names)}")
    print("step start = pipeline start + the 'completed in' of the earlier steps (computed)")
    print()
    fmt = "{:<40} {:<9} {:<34} {:<20} {:>8}  {}"
    print(fmt.format("PROJECT", "PHASE", "CREGIT STEP", "STEP START (UTC)", "ELAPSED", "LAST LOG LINE (age)"))
    hl = re.compile(args.highlight) if args.highlight else None
    order = [n for n in names if hl and hl.search(n)] + [n for n in running if not (hl and hl.search(n))]
    for n in order:
        if n not in running:
            st = finals.get(n) or ever.get(n) or ("queued" if n in pending else "?")
            print(fmt.format(n[:40], st, "-", "-", "-", "(not running)"))
            continue
        r = last[n]
        phase = r.get("step", "?")
        step_txt, start_txt, el_txt = "-", "-", "-"
        log = newest_log(state, n, "pipeline") if phase == "pipeline" else newest_log(state, n, phase)
        if phase == "pipeline" and log:
            step, sname, start = pipeline_step(log, pipe_start.get(n))
            if step:
                step_txt = f"{step} {sname}"[:34]
                if start:
                    start_txt = f"{start:%Y-%m-%d %H:%M:%S}"
                    el_txt = fmt_age((now - start).total_seconds())
        else:
            st = parse_utc(r.get("start_utc"))
            if st:
                start_txt = f"{st:%Y-%m-%d %H:%M:%S}"
                el_txt = fmt_age((now - st).total_seconds())
        tail = ""
        if log:
            age = now.timestamp() - log.stat().st_mtime
            tail = f"{last_line(log)} ({fmt_age(age)} ago)"
        print(fmt.format(n[:40], phase, step_txt, start_txt, el_txt, tail))
    return 0


if __name__ == "__main__":
    sys.exit(main())
EOF_census-steps
chmod 755 /usr/local/bin/census-steps.new
mv -f /usr/local/bin/census-steps.new /usr/local/bin/census-steps
cat > /usr/local/bin/census-b3-parts-init.new <<'EOF_census-b3-parts-init'
#!/usr/bin/env bash
# census-b3-parts-init a|b: the census parts of this spot instance (2026-10-09 A/B test).
#   a: one part aK per XFS filesystem /dataK (no RAID; K = 1..number of instance-store disks),
#      each with its own ctp clone and state (/dataK/ctp), config and output
#      (/dataK/census-2026-10-batch3a); the 20 workers split as evenly as possible (4 disks: 5 each).
#   b: 1 part b on the RAID0 /data, the batch 2 layout: /home/ec2-user/ctp, 20 workers (control).
# Writes /etc/cregit-census/batch.env (BATCH, PARTS) and <part>.env (CTP, OUT, WORKERS, CFG, LOG),
# and the ctp clones of the a parts (the same bundle and Python pins as batch 2).
set -euo pipefail
X=$1; E=/etc/cregit-census; mkdir -p $E
case $X in
  a) parts=""; for d in /data[0-9]*; do mountpoint -q "$d" && parts="$parts a${d#/data}"; done; parts=${parts# }
     [ -n "$parts" ] || { echo "no /dataK filesystems: run layout-fsN.sh first" >&2; exit 2; } ;;
  b) parts="b" ;;
  *) echo "usage: census-b3-parts-init a|b" >&2; exit 2 ;;
esac
printf 'BATCH=%s\nPARTS="%s"\n' "$X" "$parts" > $E/batch.env
np=$(echo $parts | wc -w); i=0
for p in $parts; do
  if [ "$p" = b ]; then C=/home/ec2-user/ctp; O=/data/census-2026-10-batch3; W=20
  else k=${p#a}; C=/data$k/ctp; O=/data$k/census-2026-10-batch3a; W=$(( 20 / np + (i < 20 % np ? 1 : 0) )); fi
  i=$((i+1))
  printf 'PART=%s\nCTP=%s\nOUT=%s\nWORKERS=%s\nCFG=%s\nLOG=%s\n' "$p" "$C" "$O" "$W" "$E/$p.cfg" "/data/logs/batch3-$p.log" > $E/$p.env
  printf '# ctp config (CTP_CONFIG) for census batch3 part %s on spot: cregit 95cdc88.\n[paths]\ncregit_dir = /data/cregit-ec2\noutput_dir = %s\n' "$p" "$O" > $E/$p.cfg
  mkdir -p "$O"; chown ec2-user: "$O"
  if [ ! -x "$C/.venv/bin/python" ]; then
    sudo -u ec2-user bash -c "set -e; [ -d $C ] || git clone -q /data/input/ctp.bundle $C -b feat/e2e-runner; cd $C; [ \"\$(git rev-parse --short HEAD)\" = ca113e3 ]; python3.12 -m venv .venv; .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0"
  fi
  echo "$p: $(sudo -u ec2-user git -C $C rev-parse --short HEAD) $C -> $O, $W workers"
done
chmod 644 $E/*
EOF_census-b3-parts-init
chmod 755 /usr/local/bin/census-b3-parts-init.new
mv -f /usr/local/bin/census-b3-parts-init.new /usr/local/bin/census-b3-parts-init
cat > /usr/local/bin/census-b3-prep.new <<'EOF_census-b3-prep'
#!/usr/bin/env bash
# census-b3-prep: inputs for the census parts of this spot instance. Copies the batch 3 inputs
# to /home/ec2-user/b3-input (sha256-checked). For each part writes
#   manifest.<part>.full.tsv: the part's share of manifest.batch3<a|b>.tsv (a: rows k, k+4,
#     k+8 ... in u order for part ak; b: all rows), the same on every instance;
#   manifest.<part>.run.tsv: that minus every project with s3://BUCKET/batch3/<a|b>/done/<p>/OK.
# Refuses if batch3/<a|b>/final/DONE exists (every project of that batch is in done/).
set -euo pipefail
. /etc/cregit-census/batch.env
S3=s3://${RUNNER_BUCKET}/batch3
I=/home/ec2-user/b3-input
if aws s3 ls "$S3/$BATCH/final/DONE" >/dev/null 2>&1; then echo "$S3/$BATCH/final/DONE exists: batch3$BATCH is finished"; exit 1; fi
mkdir -p "$I"
aws s3 cp "$S3/input/" "$I/" --recursive --only-show-errors
(cd "$I" && sha256sum --quiet -c SHA256SUMS) && echo "inputs: sha256 ok"
{ aws s3 ls "$S3/$BATCH/done/" --recursive || true; } | awk '$4 ~ /\/OK$/ {n=split($4,a,"/"); print a[n-1]}' | sort -u > "$I/done.txt"
python3 - "$I" "$BATCH" "$PARTS" <<'P'
import sys, datetime
I, batch, parts = sys.argv[1], sys.argv[2], sys.argv[3].split()
src = f"{I}/manifest.batch3{batch}.tsv"
done = set(open(f"{I}/done.txt").read().split())
lines = open(src).read().splitlines()
rows = [l for l in lines if l.strip() and not l.startswith("#")]
cols = next(l for l in lines if l.startswith("# Columns:"))
now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
for k, p in enumerate(parts):
    share = rows[k::len(parts)]
    keep = [r for r in share if r.split("\t")[0] not in done]
    what = f"rows {k + 1}, {k + 1 + len(parts)}, ... (every {len(parts)}th)" if len(parts) > 1 else "all rows"
    with open(f"{I}/manifest.{p}.full.tsv", "w") as f:
        f.write(f"# Part {p} of manifest.batch3{batch}.tsv: {what}, u order.\n# {len(share)} projects.\n{cols}\n")
        f.writelines(r + "\n" for r in share)
    with open(f"{I}/manifest.{p}.run.tsv", "w") as f:
        f.write(f"# Run manifest of part {p}, written {now} by census-b3-prep: {len(keep)} of {len(share)}"
                f" projects; {len(share) - len(keep)} already in done/ are left out. u order kept.\n{cols}\n")
        f.writelines(r + "\n" for r in keep)
    print(f"{p}: {len(keep)} of {len(share)} projects to run ({len(share) - len(keep)} already done)")
P
chown -R ec2-user: "$I"
EOF_census-b3-prep
chmod 755 /usr/local/bin/census-b3-prep.new
mv -f /usr/local/bin/census-b3-prep.new /usr/local/bin/census-b3-prep
cat > /usr/local/bin/census-b3-check.new <<'EOF_census-b3-check'
#!/usr/bin/env bash
# census-b3-check: the machine-independence check before a census: libsrcml sha256 and the
# libexpat Parquet sha256 (check.sh from the batch 2 setup) must equal the reference values.
set -uo pipefail
WANT_SRCML=dea4467bb1b0a435e4536be13367325564b82e14ff69b478ad31bf144a8455f3
WANT_PQ=40511e0de1a285b5bbc4ae0ff277e4775c5d67709966dd7c64dc9163c638fc5d
cat > /home/ec2-user/srcml-sha.sh <<'U'
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cd /data/cregit-ec2
devenv shell -- bash -c 'sha256sum "$SRCML_PREFIX/lib/libsrcml.so.1.1.0"'
U
chown ec2-user: /home/ec2-user/srcml-sha.sh
got_srcml=$(sudo -u ec2-user -i bash /home/ec2-user/srcml-sha.sh 2>/dev/null | grep -o '^[0-9a-f]\{64\}' | tail -1)
echo "libsrcml.so.1.1.0 sha256 $got_srcml"
[ "$got_srcml" = "$WANT_SRCML" ] || { echo "CHECK FAILED: libsrcml sha256 differs"; exit 1; }
[ -d /data/ec2-check/out ] && mv /data/ec2-check/out "/data/ec2-check/out.old.$(date +%s)"
sudo -u ec2-user -i bash /home/ec2-user/check.sh
got_pq=$(sha256sum /data/ec2-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet 2>/dev/null | cut -d' ' -f1)
echo "libexpat Parquet sha256 $got_pq"
[ "$got_pq" = "$WANT_PQ" ] || { echo "CHECK FAILED: libexpat Parquet sha256 differs from $WANT_PQ"; exit 1; }
echo "CHECK OK"
EOF_census-b3-check
chmod 755 /usr/local/bin/census-b3-check.new
mv -f /usr/local/bin/census-b3-check.new /usr/local/bin/census-b3-check
cat > /usr/local/bin/census-b3-start.new <<'EOF_census-b3-start'
#!/usr/bin/env bash
# census-b3-start: start every census part of this spot instance: prep the run manifests, then
# the interruption watcher, the upload and live timers, and census-b3@<part> for each part with
# projects left. Run census-b3-check first (it must print CHECK OK).
set -euo pipefail
. /etc/cregit-census/batch.env
for p in $PARTS; do . /etc/cregit-census/$p.env
  [ -e "$CTP/STOP" ] && { echo "STOP exists in $CTP: not starting"; exit 1; }
  systemctl is-active --quiet census-b3@$p.service && { echo "census-b3@$p already active"; exit 1; }
done
/usr/local/bin/census-b3-prep
mkdir -p /data/logs /data/uploaded; chown ec2-user: /data/logs /data/uploaded
systemctl daemon-reload
systemctl start census-b3-watch.service census-b3-upload.timer census-b3-live.timer
for p in $PARTS; do
  n=$(grep -c -v -e '^#' -e '^[[:space:]]*$' /home/ec2-user/b3-input/manifest.$p.run.tsv || true)
  if [ "$n" -gt 0 ]; then systemctl start census-b3@$p.service; echo "started census-b3@$p ($n projects)"; else echo "$p: nothing left"; fi
done
sleep 30
systemctl is-active census-b3-watch.service census-b3-upload.timer census-b3-live.timer $(for p in $PARTS; do echo census-b3@$p.service; done)
for p in $PARTS; do tail -n 3 /data/logs/batch3-$p.log; done
EOF_census-b3-start
chmod 755 /usr/local/bin/census-b3-start.new
mv -f /usr/local/bin/census-b3-start.new /usr/local/bin/census-b3-start
cat > /usr/local/bin/census-b3-run.new <<'EOF_census-b3-run'
#!/usr/bin/env bash
# census-b3-run PART (census-b3@PART.service): one census part of batch 3a/3b on a spot instance.
# Same cregit build (95cdc88 at /data/cregit-ec2) and flags as batch 2, except --memory-limit 16GB
# (lagadic__visp failed in firm at 8 GB on batch 2) and the part's manifest and worker count.
# Stop after the running projects: touch $CTP/STOP (census-b3-watch does it on a spot notice).
set -euo pipefail
. /etc/cregit-census/batch.env; . "/etc/cregit-census/$1.env"
I=/home/ec2-user/b3-input; M="$I/manifest.$PART.run.tsv"
export CTP_CONFIG=$CFG
cd "$CTP"
echo "=== $(date -u +%FT%TZ) census batch3 part $PART start on $(cat /sys/devices/virtual/dmi/id/board_asset_tag) (cregit $(git -C /data/cregit-ec2 rev-parse --short HEAD), ctp $(git rev-parse --short HEAD), $(grep -c -v -e '^#' -e '^[[:space:]]*$' "$M") projects, $WORKERS workers, out $OUT)"
exec .venv/bin/python ctp.py census --manifest "$M" \
    --project-meta "$I/project_meta.batch3$BATCH.json" \
    --workers "$WORKERS" --retries 3 --skip-html --latest --tokenizer-worker \
    --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb 500
EOF_census-b3-run
chmod 755 /usr/local/bin/census-b3-run.new
mv -f /usr/local/bin/census-b3-run.new /usr/local/bin/census-b3-run
cat > /usr/local/bin/census-b3-upload.new <<'EOF_census-b3-upload'
#!/usr/bin/env python3
"""census-b3-upload (census-b3-upload.timer, every minute): copy each finished project to S3.

It covers every census part of the instance (/etc/cregit-census/batch.env PARTS; each part's
CTP and OUT from <part>.env). A project is finished when its last final ledger row ("project") says done or done-dirty and its
.validated stamp exists. For each one not yet uploaded it copies
  OUT/<name>/<name>-dataset.parquet, OUT/<name>/<name>.validated,
  ctp state/<name>/*.json and state/<name>/logs/* (regular files), and a ledger.jsonl snapshot
to s3://BUCKET/batch3/<a|b>/done/<name>/, lists the prefix back and compares every key and size,
then writes done/<name>/OK (time, instance, files, sizes, Parquet sha256) and a local marker in
/data/uploaded/. A restart leaves out exactly the projects that have OK.
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

def env(path):
    out = {}
    for line in Path(path).read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


BENV = env("/etc/cregit-census/batch.env")
BATCH = BENV["BATCH"]
PARTS = [(p, Path(e["CTP"]), Path(e["OUT"])) for p in BENV["PARTS"].split()
         for e in [env(f"/etc/cregit-census/{p}.env")]]
DEST = f"s3://${RUNNER_BUCKET}/batch3/{BATCH}/done"
MARK = Path("/data/uploaded")


def finished(CTP):
    final = {}
    try:
        with (CTP / "ledger.jsonl").open() as f:
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


def upload(name, part, CTP, OUT):
    pq = OUT / name / f"{name}-dataset.parquet"
    stamp = OUT / name / f"{name}.validated"
    if not (pq.is_file() and stamp.is_file()):
        return f"{name}: Parquet or stamp missing, later"
    stage = OUT.parent / "upload-stage"  # same filesystem as OUT, so os.link works
    stage.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}.", dir=stage))
    try:
        for f in (pq, stamp):
            os.link(f, tmp / f.name)
        st = CTP / "state" / name
        (tmp / "state" / "logs").mkdir(parents=True)
        for f in st.glob("*.json"):
            if f.is_file() and not f.is_symlink():
                shutil.copy2(f, tmp / "state" / f.name)
        for f in (st / "logs").glob("*"):
            if f.is_file() and not f.is_symlink():
                shutil.copy2(f, tmp / "state" / "logs" / f.name)
        shutil.copy2(CTP / "ledger.jsonl", tmp / "ledger.jsonl")
        local = {str(p.relative_to(tmp)): p.stat().st_size for p in tmp.rglob("*") if p.is_file()}
        subprocess.run(["aws", "s3", "cp", f"{tmp}/", f"{DEST}/{name}/", "--recursive",
                        "--only-show-errors"], check=True)
        ls = subprocess.run(["aws", "s3", "ls", f"{DEST}/{name}/", "--recursive"], check=True,
                            capture_output=True, text=True).stdout
        prefix = DEST.split("/", 3)[3] + f"/{name}/"
        remote = {}
        for line in ls.splitlines():
            parts = line.split(None, 3)
            if len(parts) == 4 and parts[3].startswith(prefix):
                remote[parts[3][len(prefix):]] = int(parts[2])
        bad = [k for k, v in local.items() if remote.get(k) != v]
        if bad:
            return f"{name}: size check FAILED for {bad[:5]}, will retry"
        ok = tmp / "OK"
        instance = Path("/sys/devices/virtual/dmi/id/board_asset_tag").read_text().strip()
        ok.write_text(f"uploaded {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} from {instance} part {part}\n"
                      f"parquet_sha256 {sha256(pq)}\n"
                      + "".join(f"{v}\t{k}\n" for k, v in sorted(local.items())))
        subprocess.run(["aws", "s3", "cp", str(ok), f"{DEST}/{name}/OK", "--only-show-errors"], check=True)
        MARK.mkdir(parents=True, exist_ok=True)
        (MARK / name).write_text(ok.read_text())
        return f"{name}: uploaded {len(local)} files, sizes equal, OK written"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    for part, CTP, OUT in PARTS:
      for name in finished(CTP):
        if (MARK / name).exists():
            continue
        try:
            print(time.strftime("%FT%TZ", time.gmtime()), upload(name, part, CTP, OUT), flush=True)
        except (subprocess.CalledProcessError, OSError) as e:
            print(time.strftime("%FT%TZ", time.gmtime()), f"{name}: upload error {e}, will retry", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
EOF_census-b3-upload
chmod 755 /usr/local/bin/census-b3-upload.new
mv -f /usr/local/bin/census-b3-upload.new /usr/local/bin/census-b3-upload
cat > /usr/local/bin/census-b3-live.new <<'EOF_census-b3-live'
#!/usr/bin/env bash
# Every 10 min (census-b3-live.timer): status of every census part to s3://BUCKET/batch3/<a|b>/live/:
# progress.txt (all parts: ctp progress + the step table), steps.txt, batch3-<part>.log.tail,
# ledger.<part>.jsonl, system.txt (meminfo, df, load) and upload.log.tail.
set -uo pipefail
. /etc/cregit-census/batch.env
D=s3://${RUNNER_BUCKET}/batch3/$BATCH/live
T=$(mktemp -d); trap 'rm -r "$T"' EXIT
{ echo "as of $(date -u +%FT%TZ)  batch3$BATCH on $(cat /sys/devices/virtual/dmi/id/board_asset_tag)  parts: $PARTS"
  echo "uptime: $(uptime)"
  echo "MemAvailable: $(awk '/MemAvailable/{printf "%.1f GiB", $2/1048576}' /proc/meminfo)"
  echo "uploaded to done/: $(ls /data/uploaded 2>/dev/null | wc -l)   watcher: $(systemctl is-active census-b3-watch.service)"
  for p in $PARTS; do . /etc/cregit-census/$p.env
    echo; echo "=== part $p: census-b3@$p $(systemctl is-active census-b3@$p.service) ($(systemctl show census-b3@$p.service -p Result --value)), $OUT free $(df -BG --output=avail "$OUT" | tail -1 | tr -d ' ')"
    (cd "$CTP" && CTP_CONFIG=$CFG .venv/bin/python ctp.py progress --manifest /home/ec2-user/b3-input/manifest.$p.run.tsv --last 5 2>&1)
    /usr/local/bin/census-steps "$CTP" /home/ec2-user/b3-input/manifest.$p.run.tsv --highlight '' > "$T/steps.$p.txt" 2>&1
    echo; cat "$T/steps.$p.txt"
    tail -n 300 "$LOG" > "$T/batch3-$p.log.tail" 2>/dev/null
    [ -f "$CTP/ledger.jsonl" ] && cp "$CTP/ledger.jsonl" "$T/ledger.$p.jsonl"
  done
} > "$T/progress.txt"
cat "$T"/steps.*.txt > "$T/steps.txt"; rm -f "$T"/steps.*.txt
journalctl -u census-b3-upload.service --no-pager -n 100 -o short-iso > "$T/upload.log.tail" 2>/dev/null
{ date -u +%FT%TZ; uptime; cat /proc/pressure/io /proc/pressure/cpu 2>/dev/null; cat /proc/meminfo; df -h /data /data[0-9]* / 2>/dev/null; } > "$T/system.txt"
aws s3 cp "$T/" "$D/" --recursive --only-show-errors
EOF_census-b3-live
chmod 755 /usr/local/bin/census-b3-live.new
mv -f /usr/local/bin/census-b3-live.new /usr/local/bin/census-b3-live
cat > /usr/local/bin/census-b3-watch.new <<'EOF_census-b3-watch'
#!/usr/bin/env bash
# census-b3-watch (census-b3-watch.service, root): poll IMDSv2 spot/instance-action every 5 s.
# On a notice: touch STOP in every part's ctp clone (no new project starts), write INTERRUPTED
# (time, notice, running projects) to s3://BUCKET/batch3/<a|b>/live/, upload each part's ledger,
# and run census-b3-upload once. The instance is then terminated by EC2 about 2 min later.
# Test mode: if /run/census-fake-spot-notice exists, its content is the notice; then STOP goes to
# /run/census-STOP.test.<part> instead of the ctp clones, and the S3 names get a .test suffix, so the
# census is not stopped. The fake file is removed after it is handled and watching goes on.
set -uo pipefail
. /etc/cregit-census/batch.env
D=s3://${RUNNER_BUCKET}/batch3/$BATCH/live
FAKE=/run/census-fake-spot-notice
IMDS=http://169.254.169.254/latest
handle() {  # $1 notice, $2 suffix ("" or .test)
  local notice=$1 sfx=$2 T; T=$(mktemp -d)
  for p in $PARTS; do . /etc/cregit-census/$p.env
    if [ -z "$sfx" ]; then stop=$CTP/STOP; else stop=/run/census-STOP.test.$p; fi
    touch "$stop"; chown ec2-user: "$stop"
  done
  { echo "spot interruption notice seen $(date -u +%FT%TZ) on $(cat /sys/devices/virtual/dmi/id/board_asset_tag) (batch3$BATCH)${sfx:+  TEST, census not stopped}"
    echo "notice: $notice"
    for p in $PARTS; do . /etc/cregit-census/$p.env
      echo; echo "=== part $p (STOP: $([ -z "$sfx" ] && echo "$CTP/STOP" || echo /run/census-STOP.test.$p))"
      /usr/local/bin/census-steps "$CTP" /home/ec2-user/b3-input/manifest.$p.run.tsv --highlight '' 2>&1
      [ -f "$CTP/ledger.jsonl" ] && cp "$CTP/ledger.jsonl" "$T/ledger.$p$sfx.jsonl"
    done
    echo; echo "uploaded to done/ so far: $(ls /data/uploaded 2>/dev/null | wc -l)"
  } > "$T/INTERRUPTED$sfx"
  aws s3 cp "$T/" "$D/" --recursive --only-show-errors
  echo "$(date -u +%FT%TZ) handled notice${sfx:+ (test)}: $notice"
  sudo -u ec2-user /usr/local/bin/census-b3-upload
  rm -r "$T"
}
echo "$(date -u +%FT%TZ) watching $IMDS/meta-data/spot/instance-action every 5 s (batch3$BATCH, parts $PARTS)"
while :; do
  if [ -e $FAKE ]; then handle "$(cat $FAKE)" .test; rm -f $FAKE; sleep 5; continue; fi
  tok=$(curl -s -m 2 -X PUT "$IMDS/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
  if [ -n "$tok" ]; then
    code=$(curl -s -m 2 -o /run/census-instance-action -w '%{http_code}' -H "X-aws-ec2-metadata-token: $tok" "$IMDS/meta-data/spot/instance-action")
    if [ "$code" = 200 ]; then echo "$(date -u +%FT%TZ) $(cat /run/census-instance-action)" > /run/census-spot-interrupted; handle "$(cat /run/census-instance-action)" ""; echo "real notice handled; idle until termination"; exec sleep infinity; fi
  fi
  sleep 5
done
EOF_census-b3-watch
chmod 755 /usr/local/bin/census-b3-watch.new
mv -f /usr/local/bin/census-b3-watch.new /usr/local/bin/census-b3-watch
cat > /usr/local/bin/census-b3-finalize.new <<'EOF_census-b3-finalize'
#!/usr/bin/env bash
# census-b3-finalize (census-b3-finalize.service; OnSuccess=/OnFailure= of every census-b3@<part>).
# Waits until no census part of this spot instance is active (so a part that ends early does not
# finalize alone), runs census-b3-upload once more, then copies the results of ALL parts to
# s3://BUCKET/batch3/<a|b>/final/<instance-id>/, checks every object (key and size) and SHA256SUMS
# against the local files, writes DONE there and, when every project of manifest.batch3<a|b>.tsv
# has done/<project>/OK, also batch3/<a|b>/final/DONE (the batch is complete). Then it shuts down.
# The instance was launched with shutdown behavior "terminate", so it TERMINATES (it is a one-time
# spot instance; nothing is left on it after this).
# After a real spot notice (/run/census-spot-interrupted, from census-b3-watch) it copies nothing:
# done/ has every finished project, and restart_spot.sh runs the rest.
# No shutdown if the check fails, with --dry-run, if the longest part ran < 1 h, or if
# /home/ec2-user/NO_SHUTDOWN exists.
# 2026-10-09 (batch 5): the instance may carry other censuses (batch5 / batch1rest parts,
# census-b5@<id>). It terminates only when EVERY census on it has finalized: census-spot-decide
# decides, after this finalize wrote its DONE, so the last census to finalize terminates it.
# --decide-only: print only the termination decision (census-spot-decide), copy nothing.
# --dry-run: copy to batch3/<a|b>/dryrun/ without waiting for the parts, never shut down.
#   CTP_<part>/OUT_<part> in the environment override a part's ctp clone and output dir.
set -uo pipefail
. /etc/cregit-census/batch.env
DRY=0; [ "${1:-}" = --dry-run ] && DRY=1
DECIDE=0; [ "${1:-}" = --decide-only ] && DECIDE=1
B=s3://${RUNNER_BUCKET}
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
DEST=$B/batch3/$BATCH/final/$IID; [ $DRY = 1 ] && DEST=$B/batch3/$BATCH/dryrun/$IID
S_=/data/final-stage; FLOG=/data/logs/finalize.log; TM=$(mktemp -d /tmp/finalize.XXXXXX)
exec > >(tee -a "$FLOG") 2>&1
say() { echo "[$(date -u +%FT%TZ)] finalize: $*"; }
fail() { say "FAILED: $*"; echo "finalize failed at $(date -u +%FT%TZ): $*" > "$TM/FINALIZE_FAILED"
         aws s3 cp "$TM/FINALIZE_FAILED" "$DEST/FINALIZE_FAILED" --only-show-errors; aws s3 cp "$FLOG" "$DEST/finalize.log" --only-show-errors; exit 1; }
if [ $DECIDE = 1 ]; then why=$(/usr/local/bin/census-spot-decide 2>&1); rc=$?
  say "decide-only: $why -> $([ $rc = 0 ] && echo 'would terminate' || echo 'no termination')"; exit 0; fi
part_env() { . /etc/cregit-census/$1.env; local c="CTP_$1" o="OUT_$1"; CTP=${!c:-$CTP}; OUT=${!o:-$OUT}; }
say "start dry=$DRY batch3$BATCH parts=$PARTS DEST=$DEST"
if [ $DRY = 0 ] && [ -e /run/census-spot-interrupted ]; then
  say "spot interruption notice seen ($(cat /run/census-spot-interrupted)): no final copy; done/ has the finished projects; restart with restart_spot.sh $BATCH"
  aws s3 cp "$FLOG" "$B/batch3/$BATCH/live/finalize.log" --only-show-errors; exit 0
fi
if [ $DRY = 0 ]; then
  waited=0
  while :; do
    act=""; for p in $PARTS; do case $(systemctl is-active census-b3@$p.service) in active|activating|deactivating) act="$act $p" ;; esac; done
    [ -z "$act" ] && break
    [ $waited = 0 ] && say "parts still running:$act; waiting (this unit stays active until they end)"
    waited=1; sleep 60
  done
fi
svc=""; for p in $PARTS; do svc="$svc | census-b3@$p: $(systemctl show census-b3@$p.service -p Result -p ExecMainStatus -p ExecMainExitTimestamp 2>/dev/null | tr '\n' ' ')"; done
say "parts:$svc"
sudo -u ec2-user /usr/local/bin/census-b3-upload || say "census-b3-upload returned $? (continuing)"
[ -d "$S_" ] && mv "$S_" "$S_.old.$(date +%s)"
mkdir -p "$S_/projects" "$S_/ctp" "$S_/logs" || fail "staging dir"
n=0
for p in $PARTS; do part_env $p
  for d in "$OUT"/*/; do
    [ -d "$d" ] || continue
    name=$(basename "$d"); [ "$name" = .pin-staging ] && continue
    files=$(find "$d" -maxdepth 1 -type f \( -name '*.parquet' -o -name '*.validated' \))
    [ -n "$files" ] || continue
    mkdir -p "$S_/projects/$name"; for f in $files; do cp -l "$f" "$S_/projects/$name/" 2>/dev/null || cp -p "$f" "$S_/projects/$name/" || fail "copy $f"; done; n=$((n+1))
  done
  mkdir -p "$S_/ctp/$p"
  for f in ledger.jsonl ctp.duckdb metrics.tsv resources.tsv runs.log; do [ -f "$CTP/$f" ] && { cp -p "$CTP/$f" "$S_/ctp/$p/" || fail "copy $p/$f"; }; done
  if [ -d "$CTP/state" ]; then  # absent when the part was stopped before its first project
  ( cd "$CTP" && find state -maxdepth 1 -mindepth 1 -type d | while read -r s; do
      mkdir -p "$S_/ctp/$p/$s/logs"; find "$s" -maxdepth 1 -type f -name '*.json' -exec cp -p {} "$S_/ctp/$p/$s/" \;
      [ -d "$s/logs" ] && find "$s/logs" -maxdepth 1 -type f -exec cp -p {} "$S_/ctp/$p/$s/logs/" \; ; done ) || fail "copy state $p"
  fi
  [ -f "$LOG" ] && cp -p "$LOG" "$S_/logs/"
  cp -p /home/ec2-user/b3-input/manifest.$p.full.tsv /home/ec2-user/b3-input/manifest.$p.run.tsv "$S_/logs/" 2>/dev/null
done
say "projects with a Parquet or stamp: $n"
cp -p /data/logs/build.log "$S_/logs/" 2>/dev/null
journalctl -u census-b3-upload.service -u census-b3-watch.service --no-pager -o short-iso > "$S_/logs/upload-watch.journal" 2>/dev/null
( cd "$S_" && find . -type f ! -name SHA256SUMS -printf '%P\0' | sort -z | xargs -0 -r sha256sum > SHA256SUMS ) || fail "sha256"
say "staged $(wc -l < "$S_/SHA256SUMS") files, $(du -sh "$S_" | cut -f1)"
aws s3 cp "$S_/" "$DEST/" --recursive --only-show-errors --checksum-algorithm SHA256 || fail "upload"
# Check 1: every staged file is in the bucket with the same size.
( cd "$S_" && find . -type f -printf '%P\t%s\n' | sort ) > "$TM/final.local"
aws s3 ls "$DEST/" --recursive | awk -v p="${DEST#s3://*/}/" '{k=$0; sub(/^[^ ]+ +[^ ]+ +[0-9]+ /,"",k); sub("^" p,"",k); print k "\t" $3}' | grep -v -e '^DONE	' -e '^finalize.log	' -e '^FINALIZE_FAILED	' | sort > "$TM/final.remote" || fail "list"
missing=$(comm -23 "$TM/final.local" "$TM/final.remote" | wc -l)
[ "$missing" = 0 ] || { comm -23 "$TM/final.local" "$TM/final.remote" | head; fail "$missing staged files are missing or differ in size in $DEST"; }
# Check 2: the uploaded SHA256SUMS reads back byte-identical, and the staged files still match it.
aws s3 cp "$DEST/SHA256SUMS" "$TM/final.sums" --only-show-errors && cmp "$TM/final.sums" "$S_/SHA256SUMS" || fail "SHA256SUMS read-back differs"
( cd "$S_" && sha256sum --quiet -c SHA256SUMS ) || fail "staged files changed during upload"
say "check ok: $(wc -l < "$TM/final.local") objects, sizes equal, SHA256SUMS read back identical"
{ echo "cregit census batch3$BATCH finished and copied: $(date -u +%FT%TZ)"
  echo "instance: $(cat /sys/devices/virtual/dmi/id/board_asset_tag 2>/dev/null)  dry_run=$DRY  parts: $PARTS"
  echo "parts:$svc"
  echo "projects copied: $n   files: $(wc -l < "$S_/SHA256SUMS")   uploaded to done/: $(ls /data/uploaded 2>/dev/null | wc -l)"
  for p in $PARTS; do part_env $p; echo "--- part $p: ctp progress"
    (cd "$CTP" && CTP_CONFIG=$CFG .venv/bin/python ctp.py progress --manifest ${MANIFEST:-/home/ec2-user/b3-input/manifest.$p.run.tsv} --last 3 2>&1 | head -5); done
  echo "--- SHA256SUMS"; cat "$S_/SHA256SUMS"; } > "$TM/DONE"
aws s3 cp "$TM/DONE" "$DEST/DONE" --only-show-errors && aws s3 ls "$DEST/DONE" >/dev/null || fail "DONE upload"
aws s3 cp "$FLOG" "$DEST/finalize.log" --only-show-errors
say "DONE written to $DEST/DONE"
want=$(grep -v -e '^#' -e '^[[:space:]]*$' /home/ec2-user/b3-input/manifest.batch3$BATCH.tsv | cut -f1 | sort -u)
have=$(aws s3 ls "$B/batch3/$BATCH/done/" --recursive | awk '$4 ~ /\/OK$/ {n=split($4,a,"/"); print a[n-1]}' | sort -u)
left=$(comm -23 <(echo "$want") <(echo "$have") | grep -c . || true)
if [ "$left" = 0 ] && [ $DRY = 0 ]; then
  aws s3 cp "$TM/DONE" "$B/batch3/$BATCH/final/DONE" --only-show-errors && say "every project of batch3$BATCH has done/OK: wrote $B/batch3/$BATCH/final/DONE"
else
  say "$left projects of batch3$BATCH have no done/OK yet: batch not complete (restart_spot.sh $BATCH runs them)"
fi
if [ $DRY = 1 ]; then say "dry run: no shutdown"; exit 0; fi
ran=0
for p in $PARTS; do
  st=$(systemctl show census-b3@$p.service -p ExecMainStartTimestampMonotonic --value); ex=$(systemctl show census-b3@$p.service -p ExecMainExitTimestampMonotonic --value)
  r=$(( (${ex:-0} - ${st:-0}) / 1000000 )); [ "$r" -gt "$ran" ] && ran=$r
done
if [ "$ran" -lt 3600 ]; then say "the longest part ran only ${ran}s (< 1 h): an early failure, so no shutdown; look at /data/logs/batch3-*.log"; exit 0; fi
if [ -e /home/ec2-user/NO_SHUTDOWN ]; then say "/home/ec2-user/NO_SHUTDOWN exists: no shutdown"; exit 0; fi
if ! why=$(/usr/local/bin/census-spot-decide 2>&1); then say "$why: no shutdown; the last census on this instance to finalize terminates it"; exit 0; fi
say "$why"
say "shutting down: this one-time spot instance terminates (shutdown behavior terminate)"
sync; shutdown -h now
EOF_census-b3-finalize
chmod 755 /usr/local/bin/census-b3-finalize.new
mv -f /usr/local/bin/census-b3-finalize.new /usr/local/bin/census-b3-finalize
cat > /etc/systemd/system/census-b3@.service.new <<'EOF_census-b3@.service'
[Unit]
Description=cregit census batch 3 spot, part %i (ctp census)
Wants=network-online.target
After=network-online.target nix-daemon.service
OnSuccess=census-b3-finalize.service
OnFailure=census-b3-finalize.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
ExecStart=/usr/local/bin/census-b3-run %i
StandardOutput=append:/data/logs/batch3-%i.log
StandardError=append:/data/logs/batch3-%i.log
Restart=no
# 2026-10-09: an OOM kill of one project must not stop the whole census (systemd default is stop)
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStopSec=300
EOF_census-b3@.service
chmod 644 /etc/systemd/system/census-b3@.service.new
mv -f /etc/systemd/system/census-b3@.service.new /etc/systemd/system/census-b3@.service
cat > /etc/systemd/system/census-b3-finalize.service.new <<'EOF_census-b3-finalize.service'
[Unit]
Description=cregit census batch 3 spot: copy results to S3, write DONE, terminate

[Service]
Type=oneshot
ExecStart=/usr/local/bin/census-b3-finalize
TimeoutStartSec=infinity
EOF_census-b3-finalize.service
chmod 644 /etc/systemd/system/census-b3-finalize.service.new
mv -f /etc/systemd/system/census-b3-finalize.service.new /etc/systemd/system/census-b3-finalize.service
cat > /etc/systemd/system/census-b3-live.service.new <<'EOF_census-b3-live.service'
[Unit]
Description=cregit census batch 3 spot: live status to S3

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/census-b3-live
TimeoutStartSec=300
EOF_census-b3-live.service
chmod 644 /etc/systemd/system/census-b3-live.service.new
mv -f /etc/systemd/system/census-b3-live.service.new /etc/systemd/system/census-b3-live.service
cat > /etc/systemd/system/census-b3-live.timer.new <<'EOF_census-b3-live.timer'
[Unit]
Description=cregit census batch 3 spot: live status to S3 every 10 min

[Timer]
OnActiveSec=1min
OnUnitActiveSec=10min
AccuracySec=30s
EOF_census-b3-live.timer
chmod 644 /etc/systemd/system/census-b3-live.timer.new
mv -f /etc/systemd/system/census-b3-live.timer.new /etc/systemd/system/census-b3-live.timer
cat > /etc/systemd/system/census-b3-upload.service.new <<'EOF_census-b3-upload.service'
[Unit]
Description=cregit census batch 3 spot: copy finished projects to S3 done/

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/census-b3-upload
TimeoutStartSec=3600
EOF_census-b3-upload.service
chmod 644 /etc/systemd/system/census-b3-upload.service.new
mv -f /etc/systemd/system/census-b3-upload.service.new /etc/systemd/system/census-b3-upload.service
cat > /etc/systemd/system/census-b3-upload.timer.new <<'EOF_census-b3-upload.timer'
[Unit]
Description=cregit census batch 3 spot: copy finished projects to S3 every minute

[Timer]
OnActiveSec=1min
OnUnitInactiveSec=1min
AccuracySec=10s
EOF_census-b3-upload.timer
chmod 644 /etc/systemd/system/census-b3-upload.timer.new
mv -f /etc/systemd/system/census-b3-upload.timer.new /etc/systemd/system/census-b3-upload.timer
cat > /etc/systemd/system/census-b3-watch.service.new <<'EOF_census-b3-watch.service'
[Unit]
Description=cregit census batch 3 spot: watch for a spot interruption notice (IMDSv2)
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/census-b3-watch
Restart=always
RestartSec=5
EOF_census-b3-watch.service
chmod 644 /etc/systemd/system/census-b3-watch.service.new
mv -f /etc/systemd/system/census-b3-watch.service.new /etc/systemd/system/census-b3-watch.service
X=a
set -uo pipefail
census-b3-parts-init "$X"
systemctl daemon-reload
cat /etc/cregit-census/batch.env
/usr/local/bin/census-b3-check
echo "check rc=$?"
