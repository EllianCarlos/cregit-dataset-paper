set -euo pipefail
cat > /usr/local/bin/census-b5-derive.new <<'EOF_census-b5-derive'
#!/usr/bin/env python3
"""Build batch1rest and split it and batch 5 into the census parts (2026-10-09).

Two workloads, decided by the user at 14:36 UTC:
  batch5     = manifest.batch5.tsv (rows 657-820 of frame.layer1.csv, 164 projects).
  batch1rest = the manifest.batch1.tsv projects that did not finish locally: every row
               except the 49 in batch1-finished-20261009.txt and the two that finish locally
               (SAP__project-foxhound, wolfpld__tracy). Same rows and pins as batch 1; the new
               code (cregit 95cdc88) runs them on EC2.

Where they run:
  L projects of both  -> batch5L: one census on the batch 2 on-demand instance, u order.
  S and M of both     -> 10 census parts of 4 workers, 5 on each batch 3 spot instance (a, b):
                         about 20 new workers per instance next to the CPU-light batch 3 tails
                         (main session, 2026-10-09 ~15:00 UTC; supersedes the 8-part split of 3ceea81).
Parts are balanced by predicted time (longest first, to the part that would finish first,
weighted by its workers), and every part keeps u order. Predicted time, in seconds:
  exp(-5.846 + 0.5957 ln(commits) + 0.4389 ln(tok_bytes)), commits and tok_bytes from the frame;
  a log-linear fit on 354 finished EC2 projects of batches 2, 3, 3L and 4 (R^2 0.73, 14:45 UTC).

Writes manifest.batch1rest.tsv (+ .order.tsv, project_meta), manifest.batch5L.tsv (+ project_meta),
the parts table parts.tsv (half, workload, part, workers, projects, predicted h, sha256 of the
part manifest) and parts.assign.tsv (workload, part, project), and the part manifests
manifest.<W><P>.tsv as the record.

The spot instances get only the workload manifests and the two parts files; they derive the
part manifests themselves with `split_batch5.py --derive DIR` (DIR holds manifest.<W>.tsv,
parts.tsv, parts.assign.tsv), which writes DIR/manifest.<W><P>.tsv and checks each sha256
against parts.tsv, so they are byte-identical to the record here.
"""
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLASS_COL = 4  # name url category file_filter size_class commit
FINISH_LOCALLY = ("SAP__project-foxhound", "wolfpld__tracy")
# (half, workload, part, workers): 5 parts of 4 workers per spot instance.
PARTS = [
    ("a", "batch5", "a1", 4), ("a", "batch5", "a2", 4), ("a", "batch5", "a3", 4),
    ("a", "batch1rest", "a1", 4), ("a", "batch1rest", "a2", 4),
    ("b", "batch5", "b1", 4), ("b", "batch5", "b2", 4), ("b", "batch5", "b3", 4),
    ("b", "batch1rest", "b1", 4), ("b", "batch1rest", "b2", 4),
]
FIT = (-5.846, 0.5957, 0.4389)


def read_manifest(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    cols = next(line for line in lines if line.startswith("# Columns:"))
    rows = [line for line in lines if line.strip() and not line.startswith("#")]
    return cols, rows


def name(row: str) -> str:
    return row.split("\t")[0]


def write(stem: str, head: str, cols: str, rows: list, meta: dict) -> None:
    (HERE / f"manifest.{stem}.tsv").write_text(
        head + f"# {len(rows)} projects in u order.\n{cols}\n" + "".join(r + "\n" for r in rows),
        encoding="utf-8")
    (HERE / f"project_meta.{stem}.json").write_text(
        json.dumps({name(r): meta[name(r)] for r in rows}, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")


def part_text(src: Path, part: str, workers: int, pred_h: str, names: set) -> str:
    """The part manifest: the rows of src named in names, in src (u) order. Used here and by --derive."""
    cols, rows = read_manifest(src)
    keep = [r for r in rows if name(r) in names]
    assert len(keep) == len(names), (src, part)
    return (f"# Part {part} of the S and M projects of {src.name} (sha256 "
            f"{hashlib.sha256(src.read_bytes()).hexdigest()}),\n"
            f"# balanced by predicted time ({pred_h} h for {workers} workers), u order.\n"
            f"# {len(keep)} projects in u order.\n{cols}\n" + "".join(r + "\n" for r in keep))


def read_parts(d: Path):
    parts = [line.split("\t") for line in (d / "parts.tsv").read_text(encoding="utf-8").splitlines()
             if line and not line.startswith("#")][1:]
    assign = {}
    for line in (d / "parts.assign.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        wl, p, n = line.split("\t")
        assign.setdefault((wl, p), set()).add(n)
    return parts, assign


def derive(d: Path) -> int:
    parts, assign = read_parts(d)
    bad = 0
    for half, wl, p, w, n, h, sha in parts:
        text = part_text(d / f"manifest.{wl}.tsv", p, int(w), h, assign[(wl, p)])
        got = hashlib.sha256(text.encode("utf-8")).hexdigest()
        (d / f"manifest.{wl}{p}.tsv").write_text(text, encoding="utf-8")
        ok = got == sha and len(assign[(wl, p)]) == int(n)
        bad += not ok
        print(f"{half} {wl}{p}: {n} projects, {w} workers, sha256 {'ok' if ok else 'DIFFERS ' + got}")
    return 1 if bad else 0


def counts(rows: list) -> str:
    c = {k: sum(r.split("\t")[CLASS_COL] == k for r in rows) for k in "SML"}
    return f"S {c['S']}  M {c['M']}  L {c['L']}"


def main() -> None:
    sha = {f: hashlib.sha256((HERE / f).read_bytes()).hexdigest()
           for f in ("manifest.batch1.tsv", "manifest.batch5.tsv", "batch1-finished-20261009.txt")}
    finished = {line.strip() for line in (HERE / "batch1-finished-20261009.txt").read_text().splitlines()
                if line.strip() and not line.startswith("#")}
    assert len(finished) == 49, len(finished)
    cols1, b1 = read_manifest(HERE / "manifest.batch1.tsv")
    cols5, b5 = read_manifest(HERE / "manifest.batch5.tsv")
    assert cols1 == cols5
    meta = json.loads((HERE / "project_meta.batch1.json").read_text(encoding="utf-8"))
    meta.update(json.loads((HERE / "project_meta.batch5.json").read_text(encoding="utf-8")))
    assert finished <= {name(r) for r in b1}
    rest = [r for r in b1 if name(r) not in finished and name(r) not in FINISH_LOCALLY]
    write("batch1rest",
          f"# Rows of manifest.batch1.tsv (sha256 {sha['manifest.batch1.tsv']}) that did not finish locally:\n"
          f"# without the {len(finished)} in batch1-finished-20261009.txt (sha256 {sha['batch1-finished-20261009.txt']})\n"
          f"# and {', '.join(FINISH_LOCALLY)} (they finish locally). Same rows and pins as batch 1.\n",
          cols1, rest, meta)
    order = (HERE / "manifest.batch1.order.tsv").read_text(encoding="utf-8").splitlines()
    keep = {name(r) for r in rest}
    (HERE / "manifest.batch1rest.order.tsv").write_text(
        "\n".join([order[0]] + [o for o in order[1:] if o.split("\t")[1] in keep]) + "\n", encoding="utf-8")
    print(f"batch1rest: {len(rest)} projects  {counts(rest)}")

    u = {}
    for f in ("manifest.batch1.order.tsv", "manifest.batch5.order.tsv"):
        for line in (HERE / f).read_text(encoding="utf-8").splitlines()[1:]:
            c = line.split("\t")
            u[c[1]] = float(c[4])
    frame = {r["repo_url"].rstrip("/").removesuffix(".git"): r
             for r in csv.DictReader(open(HERE / "frame.layer1.csv", encoding="utf-8"))}

    def pred(row: str) -> float:
        f = frame[row.split("\t")[1].rstrip("/").removesuffix(".git")]
        return math.exp(FIT[0] + FIT[1] * math.log(int(f["commits"]))
                        + FIT[2] * math.log(max(int(f["tok_bytes"] or 1), 1)))

    work = {"batch1rest": rest, "batch5": b5}
    large = sorted((r for rows in work.values() for r in rows if r.split("\t")[CLASS_COL] == "L"),
                   key=lambda r: u[name(r)])
    write("batch5L",
          f"# The L projects of manifest.batch1rest.tsv and manifest.batch5.tsv (sha256 {sha['manifest.batch5.tsv']}),\n"
          f"# for the census batch5L on the batch 2 on-demand instance.\n", cols5, large, meta)
    print(f"batch5L: {len(large)} projects  {counts(large)}  predicted h: "
          + ", ".join(f"{name(r)} {pred(r) / 3600:.1f}" for r in large))

    table, assign = [], []
    for wl, rows in work.items():
        parts = [(p, w) for (_, x, p, w) in PARTS if x == wl]
        small = [r for r in rows if r.split("\t")[CLASS_COL] != "L"]
        load = {p: 0.0 for p, _ in parts}
        share = {p: [] for p, _ in parts}
        workers = dict(parts)
        for r in sorted(small, key=lambda r: (-pred(r), u[name(r)])):
            p = min(load, key=lambda p: ((load[p] + pred(r)) / workers[p], p))
            load[p] += pred(r)
            share[p].append(name(r))
        assert sum(len(v) for v in share.values()) == len(small)
        for p, w in parts:
            h = f"{load[p] / 3600:.1f}"
            text = part_text(HERE / f"manifest.{wl}.tsv", p, w, h, set(share[p]))
            (HERE / f"manifest.{wl}{p}.tsv").write_text(text, encoding="utf-8")
            _, keep = read_manifest(HERE / f"manifest.{wl}{p}.tsv")
            assert all(u[name(keep[i])] <= u[name(keep[i + 1])] for i in range(len(keep) - 1))
            half = next(x for (x, y, q, _) in PARTS if y == wl and q == p)
            table.append((half, wl, p, w, len(keep), h, hashlib.sha256(text.encode("utf-8")).hexdigest()))
            assign += [(wl, p, name(r)) for r in keep]
            print(f"{half} {wl}{p}: {len(keep)} projects  {counts(keep)}  {w} workers  "
                  f"predicted {h} h of work, {load[p] / 3600 / w:.1f} h per worker")
    table.sort(key=lambda t: (t[0], t[1] != "batch5", t[2]))
    (HERE / "parts.tsv").write_text(
        "# Census parts of batch5 and batch1rest on the two spot halves (split_batch5.py). sha256 is that of\n"
        "# the part manifest manifest.<workload><part>.tsv, which split_batch5.py --derive rebuilds.\n"
        "half\tworkload\tpart\tworkers\tprojects\tpredicted_h\tsha256\n"
        + "".join("\t".join(map(str, t)) + "\n" for t in table), encoding="utf-8")
    (HERE / "parts.assign.tsv").write_text(
        "workload\tpart\tproject\n" + "".join(f"{a}\t{b}\t{c}\n" for a, b, c in assign), encoding="utf-8")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--derive"]:
        sys.exit(derive(Path(sys.argv[2])))
    main()
EOF_census-b5-derive
chmod 755 /usr/local/bin/census-b5-derive.new
mv -f /usr/local/bin/census-b5-derive.new /usr/local/bin/census-b5-derive
cat > /usr/local/bin/census-b5-parts-init.new <<'EOF_census-b5-parts-init'
#!/usr/bin/env bash
# census-b5-parts-init a|b (root): the batch5 / batch1rest census parts of this spot half, i.e. the
# rows of /home/ec2-user/s5-input/parts.tsv with half a|b (run census-b5-prep first). Each part <id>
# (= workload + part, e.g. batch5a1) gets
#   - its own sparse XFS image <host>/loop/<id>.img, loop-mounted at /w/<id> (own superblock, so its
#     own rename lock; fstab line with nofail). Hosts: a: the /dataK disks, those whose batch 3 part
#     is not active first, round-robin; b: the RAID0 /data. Size min(1200G, 90% of the host / images
#     on it); ctp --disk-floor-gb min(300, size/4).
#   - its own ctp clone /w/<id>/ctp (ca113e3 from /data/input/ctp.bundle, Python 3.12 venv);
#   - its own cregit copy /w/<id>/cregit-ec2 of the checked /data/cregit-ec2 (95cdc88), with an empty
#     tokenizeByBlobId/build; the path is fixed before the census starts (blobExec stores it);
#   - its config /etc/cregit-census/s5/<id>.cfg, env <id>.env and output /w/<id>/census-2026-10-<wl>.
# Writes /etc/cregit-census/s5/batch.env (HALF, IDS). Idempotent: existing images, mounts, clones,
# copies and env files are kept as they are (an existing env keeps its image path).
set -euo pipefail
X=${1:-}; case $X in a|b) ;; *) echo "usage: census-b5-parts-init a|b" >&2; exit 2 ;; esac
E=/etc/cregit-census/s5; I=/home/ec2-user/s5-input; mkdir -p $E
[ -f $I/parts.tsv ] || { echo "no $I/parts.tsv: run census-b5-prep $X first" >&2; exit 2; }
[ -d /data/cregit-ec2 ] || { echo "no /data/cregit-ec2" >&2; exit 2; }
mapfile -t rows < <(awk -F'\t' -v h=$X '!/^#/ && $1==h {print $2 "\t" $3 "\t" $4}' $I/parts.tsv)
[ ${#rows[@]} -gt 0 ] || { echo "no parts of half $X in parts.tsv" >&2; exit 2; }
if [ $X = a ]; then free=""; busy=""
  for d in /data[0-9]*; do mountpoint -q $d || continue
    if systemctl is-active --quiet census-b3@a${d#/data}.service; then busy="$busy $d"; else free="$free $d"; fi; done
  hosts=($free $busy)
else hosts=($(readlink -f /data)); fi
[ ${#hosts[@]} -gt 0 ] || { echo "no host filesystems" >&2; exit 2; }
ids=""; declare -A H N
i=0
for r in "${rows[@]}"; do IFS=$'\t' read -r wl part w <<<"$r"; id=$wl$part; ids="$ids $id"
  if [ -f $E/$id.env ]; then h=$(. $E/$id.env; echo $HOST); else h=${hosts[$((i % ${#hosts[@]}))]}; fi
  H[$id]=$(readlink -f $h); N[${H[$id]}]=$(( ${N[${H[$id]}]:-0} + 1 )); i=$((i+1))
done
printf 'HALF=%s\nIDS="%s"\n' "$X" "${ids# }" > $E/batch.env
for r in "${rows[@]}"; do IFS=$'\t' read -r wl part w <<<"$r"; id=$wl$part; h=${H[$id]}
  img=$h/loop/$id.img; mp=/w/$id
  if [ -f $E/$id.env ]; then . $E/$id.env; sz=$SIZE_G; fl=$FLOOR
  else hs=$(df -BG --output=size $h | tail -1 | tr -dc 0-9); sz=$(( hs * 9 / 10 / ${N[$h]} )); [ $sz -gt 1200 ] && sz=1200
       fl=$(( sz / 4 )); [ $fl -gt 300 ] && fl=300; fi
  mkdir -p $h/loop $mp
  [ -e $img ] || { truncate -s ${sz}G $img; mkfs.xfs -q -L ${id:0:12} $img; }
  grep -q "^$img " /etc/fstab || echo "$img $mp xfs loop,noatime,discard,nofail,x-systemd.requires-mounts-for=$h 0 0" >> /etc/fstab
  mountpoint -q $mp || mount $mp
  chown ec2-user: $mp
  C=$mp/ctp; D=$mp/cregit-ec2; O=$mp/census-2026-10-$wl
  sudo -u ec2-user bash -c "set -e; [ -d $C ] || git clone -q /data/input/ctp.bundle $C -b feat/e2e-runner; cd $C; [ \"\$(git rev-parse --short HEAD)\" = ca113e3 ]; [ -x .venv/bin/python ] || { python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; }; mkdir -p $O $mp/uploaded"
  if [ ! -e $D ]; then
    tar -C /data/ -cf - --exclude='cregit-ec2/tokenizeByBlobId/build/*' cregit-ec2 | tar -C $mp -xpf -
    mkdir -p $D/tokenizeByBlobId/build; chown ec2-user: $D $D/tokenizeByBlobId/build
  fi
  printf '# ctp config (CTP_CONFIG) for census part %s (%s, part %s) on spot half %s: cregit 95cdc88,\n# own copy %s, output on loop XFS %s (image %s).\n[paths]\ncregit_dir = %s\noutput_dir = %s\n' \
    $id $wl $part $X $D $mp $img $D $O > $E/$id.cfg
  [ -f $E/$id.env ] || printf 'ID=%s\nWL=%s\nPART=%s\nHALF=%s\nWORKERS=%s\nHOST=%s\nIMG=%s\nSIZE_G=%s\nFLOOR=%s\nMP=%s\nCTP=%s\nCREGIT=%s\nOUT=%s\nCFG=%s\nLOG=%s\n' \
    $id $wl $part $X $w $h $img $sz $fl $mp $C $D $O $E/$id.cfg /data/logs/b5-$id.log > $E/$id.env
  echo "$id: $(findmnt -no SOURCE $mp) $img ${sz}G floor ${fl}G fsid=$(stat -f -c %i $mp) | ctp $(sudo -u ec2-user git -C $C rev-parse --short HEAD) | cregit $(sudo -u ec2-user git -C $D rev-parse --short HEAD) dirty=$(sudo -u ec2-user git -C $D status --porcelain --untracked-files=no | wc -l) build=$(ls -A $D/tokenizeByBlobId/build | wc -l) | $w workers"
done
chmod 644 $E/*
echo "host fsids: $(for h in "${hosts[@]}"; do echo -n "$h=$(stat -f -c %i $h) "; done)"
EOF_census-b5-parts-init
chmod 755 /usr/local/bin/census-b5-parts-init.new
mv -f /usr/local/bin/census-b5-parts-init.new /usr/local/bin/census-b5-parts-init
cat > /usr/local/bin/census-b5-prep.new <<'EOF_census-b5-prep'
#!/usr/bin/env bash
# census-b5-prep [a|b] (root): inputs of the batch5 / batch1rest parts of this spot half (default: HALF
# of /etc/cregit-census/s5/batch.env). Copies s3://BUCKET/batch5/input/ to /home/ec2-user/s5-input
# (sha256-checked), derives the part manifests manifest.<id>.tsv from manifest.<workload>.tsv,
# parts.tsv and parts.assign.tsv (census-b5-derive = split_batch5.py --derive; each sha256 must equal
# parts.tsv), and writes for each part of the half manifest.<id>.run.tsv = the part manifest minus
# every project with s3://BUCKET/<workload>/<part>/done/<project>/OK (u order kept).
set -euo pipefail
export AWS_PAGER=""
X=${1:-$(. /etc/cregit-census/s5/batch.env 2>/dev/null; echo ${HALF:-})}
case $X in a|b) ;; *) echo "usage: census-b5-prep a|b" >&2; exit 2 ;; esac
B=s3://${RUNNER_BUCKET}; I=/home/ec2-user/s5-input
mkdir -p $I
aws s3 cp $B/batch5/input/ $I/ --recursive --only-show-errors
(cd $I && sha256sum --quiet -c SHA256SUMS) && echo "inputs: sha256 ok ($(grep -c . $I/SHA256SUMS) files)"
out=$(python3 -I /usr/local/bin/census-b5-derive --derive $I) || { echo "$out"; echo "DERIVE FAILED: a part manifest differs from parts.tsv"; exit 1; }
echo "$out" | grep "^$X " || true
echo "part manifests: derived, sha256 equal to parts.tsv"
awk -F'\t' -v h=$X '!/^#/ && $1==h {print $2, $3}' $I/parts.tsv | while read -r wl p; do
  { aws s3 ls "$B/$wl/$p/done/" --recursive || true; } | awk '$4 ~ /\/OK$/ {n=split($4,a,"/"); print a[n-1]}' | sort -u > $I/done.$wl$p.txt
done
python3 - $I $X <<'P'
import sys, datetime
I, X = sys.argv[1], sys.argv[2]
now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
for line in open(f"{I}/parts.tsv").read().splitlines():
    c = line.split("\t")
    if line.startswith("#") or c[0] != X:
        continue
    pid = c[1] + c[2]
    lines = open(f"{I}/manifest.{pid}.tsv").read().splitlines()
    cols = next(l for l in lines if l.startswith("# Columns:"))
    rows = [l for l in lines if l.strip() and not l.startswith("#")]
    done = set(open(f"{I}/done.{pid}.txt").read().split())
    keep = [r for r in rows if r.split("\t")[0] not in done]
    with open(f"{I}/manifest.{pid}.run.tsv", "w") as f:
        f.write(f"# Run manifest of part {pid}, written {now} by census-b5-prep: {len(keep)} of {len(rows)}"
                f" projects; {len(rows) - len(keep)} already in {c[1]}/{c[2]}/done/ are left out. u order kept.\n{cols}\n")
        f.writelines(r + "\n" for r in keep)
    print(f"{pid}: {len(keep)} of {len(rows)} projects to run ({len(rows) - len(keep)} already done)")
P
chown -R ec2-user: $I
EOF_census-b5-prep
chmod 755 /usr/local/bin/census-b5-prep.new
mv -f /usr/local/bin/census-b5-prep.new /usr/local/bin/census-b5-prep
cat > /usr/local/bin/census-b5-check.new <<'EOF_census-b5-check'
#!/usr/bin/env bash
# census-b5-check (root): the identity check of this instance's new cregit copies, run once on the
# copy of the first part (IDS of /etc/cregit-census/s5/batch.env): libsrcml.so.1.1.0 sha256 through
# the copy's own devenv shell, and the libexpat Parquet sha256 of a census with a scratch ctp clone
# /w/<id>/ctp-check and scratch output /w/<id>/libexpat-check/out (flags of the batch 2 check).
# Both must equal the reference. Writes the result to /etc/cregit-census/s5/check.result (CHECK OK).
set -uo pipefail
WANT_SRCML=dea4467bb1b0a435e4536be13367325564b82e14ff69b478ad31bf144a8455f3
WANT_PQ=40511e0de1a285b5bbc4ae0ff277e4775c5d67709966dd7c64dc9163c638fc5d
E=/etc/cregit-census/s5; . $E/batch.env; id=${IDS%% *}; . $E/$id.env
R=$E/check.result; echo "check of $CREGIT started $(date -u +%FT%TZ)" > $R
cat > /home/ec2-user/srcml-sha-b5.sh <<U
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cd $CREGIT
devenv shell -- bash -c 'sha256sum "\$SRCML_PREFIX/lib/libsrcml.so.1.1.0"'
U
cat > /home/ec2-user/check-b5.sh <<U
set -uo pipefail
C=$MP/ctp-check
[ -d \$C ] || git clone -q /data/input/ctp.bundle \$C -b feat/e2e-runner
cd \$C; [ "\$(git rev-parse --short HEAD)" = ca113e3 ] || { echo "wrong ctp HEAD"; exit 1; }
[ -x .venv/bin/python ] || { python3.12 -m venv .venv; nice -n 19 .venv/bin/pip install -q --disable-pip-version-check duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; }
printf '# libexpat check on the cregit copy %s (scratch output).\n[paths]\ncregit_dir = %s\noutput_dir = %s\n' $CREGIT $CREGIT $MP/libexpat-check/out > $E/check.cfg
export CTP_CONFIG=$E/check.cfg
[ -d $MP/libexpat-check/out ] && mv $MP/libexpat-check/out $MP/libexpat-check/out.old.\$(date +%s)
mkdir -p $MP/libexpat-check/out
.venv/bin/python ctp.py census --manifest /data/input/manifest.libexpat.tsv --project-meta /data/input/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10 > /data/logs/b5-check.log 2>&1
echo "census rc=\$?"
U
mkdir -p /data/logs; chown ec2-user: /home/ec2-user/srcml-sha-b5.sh /home/ec2-user/check-b5.sh /data/logs; touch $E/check.cfg; chmod 666 $E/check.cfg
got_s=$(sudo -u ec2-user -i bash /home/ec2-user/srcml-sha-b5.sh 2>/dev/null | grep -o '^[0-9a-f]\{64\}' | tail -1)
echo "libsrcml.so.1.1.0 sha256 $got_s (copy $CREGIT)" | tee -a $R
[ "$got_s" = "$WANT_SRCML" ] || { echo "CHECK FAILED: libsrcml sha256 differs" | tee -a $R; exit 1; }
t0=$(date +%s); sudo -u ec2-user -i bash /home/ec2-user/check-b5.sh
got=$(sha256sum $MP/libexpat-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet 2>/dev/null | cut -d' ' -f1)
echo "libexpat Parquet sha256 $got ($(( $(date +%s) - t0 )) s; cregit_dir $(grep -o '"cregit_dir": "[^"]*"' $MP/ctp-check/runs.log 2>/dev/null | tail -1))" | tee -a $R
[ "$got" = "$WANT_PQ" ] || { echo "CHECK FAILED: libexpat Parquet sha256 differs from $WANT_PQ" | tee -a $R; exit 1; }
jar() { find $1 -name '*.jar' -path '*blobExec*' -newer $1/README.md 2>/dev/null | head -1 | xargs -r sha256sum | cut -c1-16; }
ref=$(jar /data/cregit-ec2); for i in $IDS; do . $E/$i.env; [ "$(jar $CREGIT)" = "$ref" ] || { echo "CHECK FAILED: blobExec jar of $CREGIT differs" | tee -a $R; exit 1; }; done
echo "blobExec jar sha256 $ref in /data/cregit-ec2 and all $(echo $IDS | wc -w) copies" | tee -a $R
echo "CHECK OK $(date -u +%FT%TZ)" | tee -a $R
EOF_census-b5-check
chmod 755 /usr/local/bin/census-b5-check.new
mv -f /usr/local/bin/census-b5-check.new /usr/local/bin/census-b5-check
cat > /usr/local/bin/census-b5-start.new <<'EOF_census-b5-start'
#!/usr/bin/env bash
# census-b5-start (root): start the batch5 / batch1rest parts of this spot instance: census-b5-prep
# (inputs, derived part manifests, run manifests minus done/OK), then the interruption watcher, the
# upload and live timers, and census-b5@<id> for each part with projects left. Needs CHECK OK from
# census-b5-check. Adds b5 to /etc/cregit-census/censuses (read by census-spot-decide) when a part starts.
set -euo pipefail
E=/etc/cregit-census/s5; . $E/batch.env; I=/home/ec2-user/s5-input
grep -q '^CHECK OK' $E/check.result 2>/dev/null || { echo "no CHECK OK in $E/check.result: run census-b5-check first"; exit 1; }
for id in $IDS; do . $E/$id.env
  [ -e "$CTP/STOP" ] && { echo "STOP exists in $CTP: not starting"; exit 1; }
  systemctl is-active --quiet census-b5@$id.service && { echo "census-b5@$id already active"; exit 1; }
done
/usr/local/bin/census-b5-prep $HALF
mkdir -p /data/logs; chown ec2-user: /data/logs
todo=""; for id in $IDS; do n=$(grep -c -v -e '^#' -e '^[[:space:]]*$' $I/manifest.$id.run.tsv || true); [ "$n" -gt 0 ] && todo="$todo $id"; done
[ -n "$todo" ] || { echo "no part has projects left: nothing to start"; exit 0; }
touch /etc/cregit-census/censuses; grep -qx b5 /etc/cregit-census/censuses || echo b5 >> /etc/cregit-census/censuses
systemctl start census-b5-watch.service census-b5-upload.timer census-b5-live.timer
for id in $todo; do systemctl start census-b5@$id.service
  echo "started census-b5@$id ($(grep -c -v -e '^#' -e '^[[:space:]]*$' $I/manifest.$id.run.tsv) projects) $(date -u +%FT%TZ)"; done
sleep 30
systemctl is-active census-b5-watch.service census-b5-upload.timer census-b5-live.timer $(for id in $IDS; do echo census-b5@$id.service; done) | tr '\n' ' '; echo
for id in $todo; do tail -n 2 /data/logs/b5-$id.log | cut -c1-220; done
EOF_census-b5-start
chmod 755 /usr/local/bin/census-b5-start.new
mv -f /usr/local/bin/census-b5-start.new /usr/local/bin/census-b5-start
cat > /usr/local/bin/census-b5-run.new <<'EOF_census-b5-run'
#!/usr/bin/env bash
# census-b5-run ID (census-b5@ID.service): one batch5 / batch1rest census part on a spot instance, on
# its own loop XFS /w/ID with its own ctp clone, cregit copy (95cdc88) and output (see <id>.env).
# Flags of batch 3/4 on EC2. Stop after the running projects: touch $CTP/STOP (census-b5-watch does
# it on a spot notice).
set -euo pipefail
. /etc/cregit-census/s5/$1.env
I=/home/ec2-user/s5-input; M=$I/manifest.$ID.run.tsv
export CTP_CONFIG=$CFG
cd "$CTP"
echo "=== $(date -u +%FT%TZ) census $ID ($WL part $PART) start on $(cat /sys/devices/virtual/dmi/id/board_asset_tag) (cregit $(git -C "$CREGIT" rev-parse --short HEAD) at $CREGIT, ctp $(git rev-parse --short HEAD), $(grep -c -v -e '^#' -e '^[[:space:]]*$' "$M") projects, $WORKERS workers, out $OUT, floor ${FLOOR}G)"
exec .venv/bin/python ctp.py census --manifest "$M" --project-meta "$I/project_meta.$WL.json" \
    --workers "$WORKERS" --retries 3 --skip-html --latest --tokenizer-worker \
    --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb "$FLOOR"
EOF_census-b5-run
chmod 755 /usr/local/bin/census-b5-run.new
mv -f /usr/local/bin/census-b5-run.new /usr/local/bin/census-b5-run
cat > /usr/local/bin/census-b5-upload.new <<'EOF_census-b5-upload'
#!/usr/bin/env python3
"""census-b5-upload (census-b5-upload.timer, every minute): copy each finished project to S3.

It covers every batch5 / batch1rest part of this spot instance (/etc/cregit-census/s5/batch.env IDS;
each part's WL, PART, CTP, OUT, MP from <id>.env). A project is finished when its last final ledger
row ("project") says done or done-dirty and its .validated stamp exists. For each one not yet
uploaded it copies OUT/<name>/<name>-dataset.parquet, OUT/<name>/<name>.validated, ctp
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
    ids = env("/etc/cregit-census/s5/batch.env")["IDS"].split()
    return [env(f"/etc/cregit-census/s5/{i}.env") for i in ids]


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
EOF_census-b5-upload
chmod 755 /usr/local/bin/census-b5-upload.new
mv -f /usr/local/bin/census-b5-upload.new /usr/local/bin/census-b5-upload
