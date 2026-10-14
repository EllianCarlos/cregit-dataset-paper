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
set -euo pipefail
[ -e /usr/local/bin/census-b3-finalize.orig-b3only ] || cp -p /usr/local/bin/census-b3-finalize /usr/local/bin/census-b3-finalize.orig-b3only
cat > /usr/local/bin/census-b5-live.new <<'EOF_census-b5-live'
#!/usr/bin/env bash
# Every 10 min (census-b5-live.timer, ec2-user; census-b5-trim runs before it as root): status of the
# batch5 / batch1rest parts of this spot instance to each part's s3://BUCKET/<workload>/<part>/live/:
#   progress.txt  the one combined view of the instance (the same file in every part's live/). Its
#                 first line is "as of <ts>  census-b5 on <iid> (spot <x>): <state> ( <id>=<unit state> ... )
#                 finalize=<state>  batch3=<state>"; <state> is "active" while any part or the
#                 finalize runs (the local watchdog greps ": active"), then "finalized" (every part
#                 has its final DONE) or "stopped". Then load, memory, disks, and per part: unit,
#                 free space, ctp progress and the step table.
#   steps.txt     this part's step table;  <id>.log.tail;  ledger.jsonl;  system.txt (the instance).
set -uo pipefail
export AWS_PAGER=""
E=/etc/cregit-census/s5; . $E/batch.env
B=s3://${RUNNER_BUCKET}; I=/home/ec2-user/s5-input
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
T=$(mktemp -d); trap 'rm -r "$T"' EXIT
st=""; any=no; fin=yes
for id in $IDS; do s=$(systemctl is-active census-b5@$id.service); st="$st $id=$s"
  case $s in active|activating|deactivating) any=yes ;; esac
  [ -e /w/$id/final-DONE ] || fin=no; done
fz=$(systemctl is-active census-b5-finalize.service); case $fz in active|activating) any=yes ;; esac
if [ $any = yes ]; then state=active; elif [ $fin = yes ]; then state=finalized; else state=stopped; fi
b3=none; if grep -qx b3 /etc/cregit-census/censuses 2>/dev/null; then . /etc/cregit-census/batch.env; b3=inactive
  for p in $PARTS; do case $(systemctl is-active census-b3@$p.service) in active|activating|deactivating) b3=active ;; esac; done; fi
for id in $IDS; do . $E/$id.env
  /usr/local/bin/census-steps "$CTP" $I/manifest.$id.run.tsv --highlight '' > "$T/steps.$id.txt" 2>&1; done
{ echo "as of $(date -u +%FT%TZ)  census-b5 on $IID (spot $HALF): $state ($st )  finalize=$fz  batch3=$b3$([ -e /home/ec2-user/NO_SHUTDOWN ] && echo '  NO_SHUTDOWN')"
  echo "uptime: $(uptime)"
  echo "MemAvailable: $(awk '/MemAvailable/{printf "%.1f GiB", $2/1048576}' /proc/meminfo)   watcher: $(systemctl is-active census-b5-watch.service)"
  echo "uploaded to done/: $(cat /w/*/uploaded/* 2>/dev/null | grep -c '^uploaded ')   hosts: $(df -BG --output=target,avail $(for id in $IDS; do . $E/$id.env; echo $HOST; done | sort -u) | tail -n +2 | tr -s ' ' | tr '\n' ' ')"
  for id in $IDS; do . $E/$id.env
    echo; echo "=== part $id ($WL/$PART): census-b5@$id $(systemctl is-active census-b5@$id.service) ($(systemctl show census-b5@$id.service -p Result --value)), $MP free $(df -BG --output=avail $MP | tail -1 | tr -d ' '), image $(du -BG $IMG | cut -f1)$([ -e $CTP/STOP ] && echo '  STOP present')$([ -e $MP/final-DONE ] && echo '  final DONE')"
    (cd "$CTP" && CTP_CONFIG=$CFG .venv/bin/python ctp.py progress --manifest $I/manifest.$id.run.tsv --last 5 2>&1)
    echo; cat "$T/steps.$id.txt"
  done
} > "$T/progress.txt"
{ date -u +%FT%TZ; uptime; cat /proc/pressure/io /proc/pressure/cpu 2>/dev/null; cat /proc/meminfo; df -h /data /data[0-9]* /w/* / 2>/dev/null; du -h /data*/loop/*.img 2>/dev/null; } > "$T/system.txt"
for id in $IDS; do . $E/$id.env; mkdir -p $T/p/$id
  cp $T/progress.txt $T/system.txt $T/p/$id/; cp $T/steps.$id.txt $T/p/$id/steps.txt
  tail -n 300 "$LOG" > $T/p/$id/$id.log.tail 2>/dev/null
  [ -f "$CTP/ledger.jsonl" ] && cp "$CTP/ledger.jsonl" $T/p/$id/ledger.jsonl
  aws s3 cp $T/p/$id/ "$B/$WL/$PART/live/" --recursive --only-show-errors
done
EOF_census-b5-live
chmod 755 /usr/local/bin/census-b5-live.new
mv -f /usr/local/bin/census-b5-live.new /usr/local/bin/census-b5-live
cat > /usr/local/bin/census-b5-trim.new <<'EOF_census-b5-trim'
#!/usr/bin/env bash
# census-b5-trim (root, before every census-b5-live): fstrim each part's loop XFS /w/<id>, so blocks
# freed inside (cleaned-up clones) are punched out of the sparse image and the host disk gets them back.
. /etc/cregit-census/s5/batch.env
for id in $IDS; do mountpoint -q /w/$id && fstrim /w/$id >/dev/null 2>&1; done
exit 0
EOF_census-b5-trim
chmod 755 /usr/local/bin/census-b5-trim.new
mv -f /usr/local/bin/census-b5-trim.new /usr/local/bin/census-b5-trim
cat > /usr/local/bin/census-b5-watch.new <<'EOF_census-b5-watch'
#!/usr/bin/env bash
# census-b5-watch (census-b5-watch.service, root): poll IMDSv2 spot/instance-action every 5 s.
# On a notice: touch STOP in every batch5 / batch1rest part's ctp clone (no new project starts),
# write INTERRUPTED (time, notice, running projects) and the part's ledger to each part's
# s3://BUCKET/<workload>/<part>/live/, and run census-b5-upload once. EC2 terminates the instance
# about 2 min later; restart_spot.sh relaunches every unfinished workload of the half.
# (census-b3-watch does the same for the batch 3 parts, when they run here.)
# Test mode: if /run/census-b5-fake-spot-notice exists, its content is the notice; STOP then goes to
# /run/census-b5-STOP.test.<id> instead of the ctp clones and the S3 names get a .test suffix, so the
# census is not stopped. The fake file is removed after it is handled and watching goes on.
set -uo pipefail
export AWS_PAGER=""
E=/etc/cregit-census/s5; . $E/batch.env
B=s3://${RUNNER_BUCKET}
FAKE=/run/census-b5-fake-spot-notice
IMDS=http://169.254.169.254/latest
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
handle() {  # $1 notice, $2 suffix ("" or .test)
  local notice=$1 sfx=$2 T id; T=$(mktemp -d)
  for id in $IDS; do . $E/$id.env
    if [ -z "$sfx" ]; then stop=$CTP/STOP; else stop=/run/census-b5-STOP.test.$id; fi
    touch "$stop"; chown ec2-user: "$stop"
  done
  for id in $IDS; do . $E/$id.env; mkdir -p $T/$id
    { echo "spot interruption notice seen $(date -u +%FT%TZ) on $IID (spot $HALF, part $id)${sfx:+  TEST, census not stopped}"
      echo "notice: $notice"
      echo "STOP: $([ -z "$sfx" ] && echo "$CTP/STOP" || echo /run/census-b5-STOP.test.$id)"
      /usr/local/bin/census-steps "$CTP" /home/ec2-user/s5-input/manifest.$id.run.tsv --highlight '' 2>&1
      echo "uploaded to done/ so far: $(ls $MP/uploaded 2>/dev/null | wc -l)"
    } > "$T/$id/INTERRUPTED$sfx"
    [ -f "$CTP/ledger.jsonl" ] && cp "$CTP/ledger.jsonl" "$T/$id/ledger$sfx.jsonl"
    aws s3 cp "$T/$id/" "$B/$WL/$PART/live/" --recursive --only-show-errors
  done
  echo "$(date -u +%FT%TZ) handled notice${sfx:+ (test)}: $notice"
  sudo -u ec2-user /usr/local/bin/census-b5-upload
  rm -r "$T"
}
echo "$(date -u +%FT%TZ) watching $IMDS/meta-data/spot/instance-action every 5 s (spot $HALF, parts $IDS)"
while :; do
  if [ -e $FAKE ]; then handle "$(cat $FAKE)" .test; rm -f $FAKE; sleep 5; continue; fi
  tok=$(curl -s -m 2 -X PUT "$IMDS/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
  if [ -n "$tok" ]; then
    code=$(curl -s -m 2 -o /run/census-b5-instance-action -w '%{http_code}' -H "X-aws-ec2-metadata-token: $tok" "$IMDS/meta-data/spot/instance-action")
    if [ "$code" = 200 ]; then echo "$(date -u +%FT%TZ) $(cat /run/census-b5-instance-action)" > /run/census-spot-interrupted
      handle "$(cat /run/census-b5-instance-action)" ""; echo "real notice handled; idle until termination"; exec sleep infinity; fi
  fi
  sleep 5
done
EOF_census-b5-watch
chmod 755 /usr/local/bin/census-b5-watch.new
mv -f /usr/local/bin/census-b5-watch.new /usr/local/bin/census-b5-watch
cat > /usr/local/bin/census-b5-finalize.new <<'EOF_census-b5-finalize'
#!/usr/bin/env bash
# census-b5-finalize (census-b5-finalize.service; OnSuccess=/OnFailure= of every census-b5@<id>).
# Waits until no batch5 / batch1rest part of this spot instance is active (a part that ends early
# does not finalize alone), runs census-b5-upload once more, then for EACH part copies its results to
# s3://BUCKET/<workload>/<part>/final/<instance-id>/ (Parquet and .validated per project, the ctp
# ledger, duckdb, state json and logs, the census log, the part and run manifests), checks every
# object (key and size) and that SHA256SUMS reads back byte-identical, and writes DONE there; when
# every project of the part manifest has done/<project>/OK it also writes <workload>/<part>/final/DONE.
# Then it terminates the instance (shutdown; shutdown behavior terminate) only if EVERY census on it
# has finalized: census-spot-decide (batch 3 parts too, when they run here).
# No shutdown if a part's copy failed, with --dry-run, if the longest part ran < 1 h and no project
# of this instance reached done/OK (an early failure), or if /home/ec2-user/NO_SHUTDOWN exists.
# After a real spot notice (/run/census-spot-interrupted) it copies nothing: done/ has every finished
# project and restart_spot.sh relaunches the rest.
# --dry-run: copy to <workload>/<part>/dryrun/<instance-id>/ without waiting, never shut down.
# --decide-only: print only the termination decision (census-spot-decide), copy nothing.
set -uo pipefail
export AWS_PAGER=""
E=/etc/cregit-census/s5; . $E/batch.env
DRY=0; [ "${1:-}" = --dry-run ] && DRY=1
DECIDE=0; [ "${1:-}" = --decide-only ] && DECIDE=1
B=s3://${RUNNER_BUCKET}; I=/home/ec2-user/s5-input
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
FLOG=/data/logs/finalize-b5.log; TM=$(mktemp -d /tmp/finalize-b5.XXXXXX)
exec > >(tee -a "$FLOG") 2>&1
say() { echo "[$(date -u +%FT%TZ)] finalize-b5: $*"; }
if [ $DECIDE = 1 ]; then why=$(/usr/local/bin/census-spot-decide 2>&1); rc=$?
  say "decide-only: $why -> $([ $rc = 0 ] && echo 'would terminate' || echo 'no termination')"; exit 0; fi
say "start dry=$DRY spot $HALF parts=$IDS"
first=${IDS%% *}
if [ $DRY = 0 ] && [ -e /run/census-spot-interrupted ]; then
  say "spot interruption notice seen ($(cat /run/census-spot-interrupted)): no final copy; done/ has the finished projects; restart with restart_spot.sh $HALF"
  (. $E/$first.env; aws s3 cp "$FLOG" "$B/$WL/$PART/live/finalize-b5.log" --only-show-errors); exit 0
fi
if [ $DRY = 0 ]; then
  waited=0
  while :; do
    act=""; for id in $IDS; do case $(systemctl is-active census-b5@$id.service) in active|activating|deactivating) act="$act $id" ;; esac; done
    [ -z "$act" ] && break
    [ $waited = 0 ] && say "parts still running:$act; waiting (this unit stays active until they end)"
    waited=1; sleep 60
  done
fi
sudo -u ec2-user /usr/local/bin/census-b5-upload || say "census-b5-upload returned $? (continuing)"
finalize_part() {  # $1 = id; returns 1 on a failed copy or check
  local id=$1 n=0 S_ DEST d name files f; . $E/$id.env
  DEST=$B/$WL/$PART/final/$IID; [ $DRY = 1 ] && DEST=$B/$WL/$PART/dryrun/$IID
  pfail() { say "$id FAILED: $*"; echo "finalize failed at $(date -u +%FT%TZ): $*" > "$TM/FINALIZE_FAILED.$id"
            aws s3 cp "$TM/FINALIZE_FAILED.$id" "$DEST/FINALIZE_FAILED" --only-show-errors; return 1; }
  local svc="census-b5@$id: $(systemctl show census-b5@$id.service -p Result -p ExecMainStatus -p ExecMainExitTimestamp 2>/dev/null | tr '\n' ' ')"
  S_=$MP/final-stage; [ -d "$S_" ] && mv "$S_" "$S_.old.$(date +%s)"
  mkdir -p "$S_/projects" "$S_/ctp" "$S_/logs" || { pfail "staging dir"; return 1; }
  for d in "$OUT"/*/; do
    [ -d "$d" ] || continue
    name=$(basename "$d"); [ "$name" = .pin-staging ] && continue
    files=$(find "$d" -maxdepth 1 -type f \( -name '*.parquet' -o -name '*.validated' \))
    [ -n "$files" ] || continue
    mkdir -p "$S_/projects/$name"; for f in $files; do cp -l "$f" "$S_/projects/$name/" 2>/dev/null || cp -p "$f" "$S_/projects/$name/" || { pfail "copy $f"; return 1; }; done; n=$((n+1))
  done
  for f in ledger.jsonl ctp.duckdb metrics.tsv resources.tsv runs.log; do [ -f "$CTP/$f" ] && { cp -p "$CTP/$f" "$S_/ctp/" || { pfail "copy $f"; return 1; }; }; done
  if [ -d "$CTP/state" ]; then
    ( cd "$CTP" && find state -maxdepth 1 -mindepth 1 -type d | while read -r s; do
        mkdir -p "$S_/ctp/$s/logs"; find "$s" -maxdepth 1 -type f -name '*.json' -exec cp -p {} "$S_/ctp/$s/" \;
        [ -d "$s/logs" ] && find "$s/logs" -maxdepth 1 -type f -exec cp -p {} "$S_/ctp/$s/logs/" \; ; done ) || { pfail "copy state"; return 1; }
  fi
  [ -f "$LOG" ] && cp -p "$LOG" "$S_/logs/"
  cp -p $I/manifest.$id.tsv $I/manifest.$id.run.tsv $E/$id.env $E/$id.cfg "$S_/logs/" 2>/dev/null
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
    echo "instance: $IID  spot $HALF  dry_run=$DRY"
    echo "$svc"
    echo "projects copied: $n   files: $(wc -l < "$S_/SHA256SUMS")   uploaded to done/ by this instance: $(ls $MP/uploaded 2>/dev/null | wc -l)"
    (cd "$CTP" && CTP_CONFIG=$CFG .venv/bin/python ctp.py progress --manifest $I/manifest.$id.run.tsv --last 3 2>&1 | head -5)
    echo "--- SHA256SUMS"; cat "$S_/SHA256SUMS"; } > "$TM/DONE.$id"
  aws s3 cp "$TM/DONE.$id" "$DEST/DONE" --only-show-errors && aws s3 ls "$DEST/DONE" >/dev/null || { pfail "DONE upload"; return 1; }
  say "$id: DONE written to $DEST/DONE"
  [ $DRY = 0 ] && cp "$TM/DONE.$id" $MP/final-DONE
  local want have left
  want=$(grep -v -e '^#' -e '^[[:space:]]*$' $I/manifest.$id.tsv | cut -f1 | sort -u)
  have=$(aws s3 ls "$B/$WL/$PART/done/" --recursive | awk '$4 ~ /\/OK$/ {n=split($4,a,"/"); print a[n-1]}' | sort -u)
  left=$(comm -23 <(echo "$want") <(echo "$have") | grep -c . || true)
  if [ "$left" = 0 ] && [ $DRY = 0 ]; then
    aws s3 cp "$TM/DONE.$id" "$B/$WL/$PART/final/DONE" --only-show-errors && say "$id: every project of the part has done/OK: wrote $B/$WL/$PART/final/DONE"
  else say "$id: $left projects of the part have no done/OK yet (restart_spot.sh $HALF runs them)"; fi
  return 0
}
bad=""
for id in $IDS; do finalize_part $id || bad="$bad $id"; done
(. $E/$first.env; aws s3 cp "$FLOG" "$B/$WL/$PART/$([ $DRY = 1 ] && echo dryrun || echo final)/$IID/finalize-b5.log" --only-show-errors)
if [ $DRY = 1 ]; then why=$(/usr/local/bin/census-spot-decide 2>&1); rc=$?
  say "dry run: no shutdown (a real run would: $why -> $([ $rc = 0 ] && echo terminate || echo 'no termination'))"; exit 0; fi
[ -z "$bad" ] || { say "the final copy failed for:$bad: no shutdown; look at $FLOG"; exit 1; }
ran=0; up=$(cat /w/*/uploaded/* 2>/dev/null | grep -c '^uploaded ')
for id in $IDS; do
  st=$(systemctl show census-b5@$id.service -p ExecMainStartTimestampMonotonic --value); ex=$(systemctl show census-b5@$id.service -p ExecMainExitTimestampMonotonic --value)
  r=$(( (${ex:-0} - ${st:-0}) / 1000000 )); [ "$r" -gt "$ran" ] && ran=$r
done
if [ "$ran" -lt 3600 ] && [ "$up" = 0 ]; then say "the longest part ran only ${ran}s (< 1 h) and no project reached done/OK: an early failure, so no shutdown; look at /data/logs/b5-*.log"; exit 0; fi
if [ -e /home/ec2-user/NO_SHUTDOWN ]; then say "/home/ec2-user/NO_SHUTDOWN exists: no shutdown"; exit 0; fi
if ! why=$(/usr/local/bin/census-spot-decide 2>&1); then say "$why: no shutdown; the last census on this instance to finalize terminates it"; exit 0; fi
say "$why"
say "shutting down: this one-time spot instance terminates (shutdown behavior terminate)"
sync; shutdown -h now
EOF_census-b5-finalize
chmod 755 /usr/local/bin/census-b5-finalize.new
mv -f /usr/local/bin/census-b5-finalize.new /usr/local/bin/census-b5-finalize
cat > /usr/local/bin/census-spot-decide.new <<'EOF_census-spot-decide'
#!/usr/bin/env bash
# census-spot-decide (2026-10-09): exit 0 when EVERY census on this spot instance has finalized, so
# the instance may terminate; otherwise print why not and exit 1. Called by census-b3-finalize and
# census-b5-finalize just before they would shut down (shutdown behavior terminate); each writes its
# own DONE first, so only the last census to finalize terminates the instance.
# The censuses of this instance are the words in /etc/cregit-census/censuses (default "b3", the
# batch 3 rule before 2026-10-09):
#   b3: no census-b3@<part> (PARTS of /etc/cregit-census/batch.env) is active, and
#       s3://BUCKET/batch3/<a|b>/final/<instance-id>/DONE exists (census-b3-finalize, after its check);
#   b5: no census-b5@<id> (IDS of /etc/cregit-census/s5/batch.env) is active, and for every part
#       s3://BUCKET/<workload>/<part>/final/<instance-id>/DONE exists (census-b5-finalize).
# Test overrides: CENSUSES (the list), IID, BUCKET_DONE (prefix used for the DONE lookups instead of
# s3://BUCKET; e.g. a dry-run prefix), UNITS_b3 / UNITS_b5 (space-separated units; "" = none).
set -uo pipefail
export AWS_PAGER=""
B=${BUCKET_DONE:-s3://${RUNNER_BUCKET}}
IID=${IID:-$(cat /sys/devices/virtual/dmi/id/board_asset_tag)}
CENSUSES=${CENSUSES-$(cat /etc/cregit-census/censuses 2>/dev/null || echo b3)}
[ -n "$(echo $CENSUSES)" ] || CENSUSES=b3
ok=""
for c in $CENSUSES; do
  case $c in
    b3) . /etc/cregit-census/batch.env
        units=${UNITS_b3-$(for p in $PARTS; do echo census-b3@$p.service; done)}
        urls="$B/batch3/$BATCH/final/$IID/DONE" ;;
    b5) . /etc/cregit-census/s5/batch.env
        units=${UNITS_b5-$(for i in $IDS; do echo census-b5@$i.service; done)}
        urls=$(for i in $IDS; do . /etc/cregit-census/s5/$i.env; echo "$B/$WL/$PART/final/$IID/DONE"; done) ;;
    *) echo "unknown census '$c' in /etc/cregit-census/censuses"; exit 2 ;;
  esac
  for u in $units; do s=$(systemctl is-active "$u")
    case $s in active|activating|reloading|deactivating) echo "census $c not finalized: $u is $s"; exit 1 ;; esac; done
  for url in $urls; do aws s3 ls "$url" >/dev/null 2>&1 || { echo "census $c not finalized: $url is missing"; exit 1; }; done
  ok="$ok $c($(echo $urls | wc -w) DONE)"
done
echo "every census on this instance finalized:$ok (units not active, DONE in S3)"
EOF_census-spot-decide
chmod 755 /usr/local/bin/census-spot-decide.new
mv -f /usr/local/bin/census-spot-decide.new /usr/local/bin/census-spot-decide
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
cat > /etc/systemd/system/census-b5@.service.new <<'EOF_census-b5@.service'
[Unit]
Description=cregit census batch5/batch1rest spot part %i (ctp census, own loop XFS /w/%i)
Wants=network-online.target
After=network-online.target nix-daemon.service
RequiresMountsFor=/w/%i
OnSuccess=census-b5-finalize.service
OnFailure=census-b5-finalize.service

[Service]
Type=simple
User=ec2-user
Group=ec2-user
WorkingDirectory=/w/%i/ctp
ExecStart=/usr/local/bin/census-b5-run %i
StandardOutput=append:/data/logs/b5-%i.log
StandardError=append:/data/logs/b5-%i.log
Restart=no
# an OOM kill of one project must not stop the whole census (systemd default is stop)
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
TasksMax=infinity
TimeoutStopSec=300
EOF_census-b5@.service
chmod 644 /etc/systemd/system/census-b5@.service.new
mv -f /etc/systemd/system/census-b5@.service.new /etc/systemd/system/census-b5@.service
cat > /etc/systemd/system/census-b5-finalize.service.new <<'EOF_census-b5-finalize.service'
[Unit]
Description=cregit census batch5/batch1rest spot: wait for all parts, copy results to S3, write DONE, terminate if every census on the instance finalized

[Service]
Type=oneshot
ExecStart=/usr/local/bin/census-b5-finalize
TimeoutStartSec=infinity
EOF_census-b5-finalize.service
chmod 644 /etc/systemd/system/census-b5-finalize.service.new
mv -f /etc/systemd/system/census-b5-finalize.service.new /etc/systemd/system/census-b5-finalize.service
cat > /etc/systemd/system/census-b5-live.service.new <<'EOF_census-b5-live.service'
[Unit]
Description=cregit census batch5/batch1rest spot: live status to S3

[Service]
Type=oneshot
User=ec2-user
# fstrim of the loop filesystems needs root ("+"): it hands freed blocks back to the host disk
ExecStartPre=+/usr/local/bin/census-b5-trim
ExecStart=/usr/local/bin/census-b5-live
TimeoutStartSec=600
EOF_census-b5-live.service
chmod 644 /etc/systemd/system/census-b5-live.service.new
mv -f /etc/systemd/system/census-b5-live.service.new /etc/systemd/system/census-b5-live.service
cat > /etc/systemd/system/census-b5-live.timer.new <<'EOF_census-b5-live.timer'
[Unit]
Description=cregit census batch5/batch1rest spot: live status to S3 every 10 min

[Timer]
OnActiveSec=1min
OnUnitActiveSec=10min
AccuracySec=30s
EOF_census-b5-live.timer
chmod 644 /etc/systemd/system/census-b5-live.timer.new
mv -f /etc/systemd/system/census-b5-live.timer.new /etc/systemd/system/census-b5-live.timer
cat > /etc/systemd/system/census-b5-upload.service.new <<'EOF_census-b5-upload.service'
[Unit]
Description=cregit census batch5/batch1rest spot: copy finished projects to S3 <workload>/<part>/done/

[Service]
Type=oneshot
User=ec2-user
ExecStart=/usr/local/bin/census-b5-upload
TimeoutStartSec=3600
EOF_census-b5-upload.service
chmod 644 /etc/systemd/system/census-b5-upload.service.new
mv -f /etc/systemd/system/census-b5-upload.service.new /etc/systemd/system/census-b5-upload.service
cat > /etc/systemd/system/census-b5-upload.timer.new <<'EOF_census-b5-upload.timer'
[Unit]
Description=cregit census batch5/batch1rest spot: copy finished projects to S3 every minute

[Timer]
OnActiveSec=1min
OnUnitActiveSec=1min
AccuracySec=10s
EOF_census-b5-upload.timer
chmod 644 /etc/systemd/system/census-b5-upload.timer.new
mv -f /etc/systemd/system/census-b5-upload.timer.new /etc/systemd/system/census-b5-upload.timer
cat > /etc/systemd/system/census-b5-watch.service.new <<'EOF_census-b5-watch.service'
[Unit]
Description=cregit census batch5/batch1rest spot: watch for a spot interruption notice (IMDSv2)
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/census-b5-watch
Restart=always
RestartSec=5
EOF_census-b5-watch.service
chmod 644 /etc/systemd/system/census-b5-watch.service.new
mv -f /etc/systemd/system/census-b5-watch.service.new /etc/systemd/system/census-b5-watch.service
echo "s5 files installed: $(sha256sum /usr/local/bin/census-b3-finalize /usr/local/bin/census-spot-decide /usr/local/bin/census-b5-finalize | cut -c1-12 | tr "\n" " ")"
