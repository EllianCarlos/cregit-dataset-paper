set -euo pipefail
cat > /usr/local/bin/census-fed-common.new <<'EOF_census-fed-common'
# census-fed-common (sourced by the census-fed-* scripts; 2026-10-09 ~20:00 UTC). The fed spot parts:
# census parts of later batches (batch 6 first) that start on this spot instance one by one, each
# when a running part (census-b5@ or census-fed@) ends, from a local queue.
#   /etc/cregit-census/fed/half          a|b (the spot half of this instance)
#   /etc/cregit-census/fed/queue         queued parts, one "<workload> <part>" per line, next first
#   /etc/cregit-census/fed/started       the ids (<workload><part>) started on this instance, in order
#   /etc/cregit-census/fed/<id>.env|cfg  each part (same keys as the census-b5 parts)
#   /etc/cregit-census/fed/PAUSE         holds the feeder (written by hand, or by a failed check)
#   /etc/cregit-census/fed/slots         parts that may run at once (census-b5@ + census-fed@), default 5
#   /home/ec2-user/fed-input/<workload>/ the inputs of s3://BUCKET/<workload>/input/ and the derived
#                                        part manifests manifest.<id>.tsv and run manifests manifest.<id>.run.tsv
# Test overrides: FED_DIR (instead of /etc/cregit-census/fed), FED_INPUT (instead of /home/ec2-user/fed-input).
FED=${FED_DIR:-/etc/cregit-census/fed}
FI=${FED_INPUT:-/home/ec2-user/fed-input}
BUCKET=s3://${RUNNER_BUCKET}
export AWS_PAGER=""
fed_half() { cat $FED/half 2>/dev/null || (. /etc/cregit-census/s5/batch.env 2>/dev/null; echo ${HALF:-}); }
fed_started() { cat $FED/started 2>/dev/null; }
fed_active() { case $(systemctl is-active "$1" 2>/dev/null) in active|activating|deactivating|reloading) return 0 ;; esac; return 1; }
nrows() { grep -c -v -e '^#' -e '^[[:space:]]*$' "$1" 2>/dev/null || true; }
oks() { { aws s3 ls "$1" --recursive </dev/null 2>/dev/null || true; } | awk '$4 ~ /\/OK$/ {n=split($4,a,"/"); print a[n-1]}' | sort -u; }
EOF_census-fed-common
chmod 755 /usr/local/bin/census-fed-common.new
mv -f /usr/local/bin/census-fed-common.new /usr/local/bin/census-fed-common
cat > /usr/local/bin/census-fed-derive.new <<'EOF_census-fed-derive'
#!/usr/bin/env python3
"""Split batch N (N >= 6) into the fed spot parts and the L census (2026-10-09, batch 6 first).

Decided by the user ~19:25 UTC ("Prepare now, start as parts drain"): the S and M projects of
manifest.batchN.tsv run as census parts of 4 workers on the two spot instances, fed one by one:
when a part on an instance ends, the next queued part of that instance starts in its place
(census-fed-feeder). The L projects run as census batchNL on the big on-demand EC2 once its
batch 4 parts free slots (census-batchNL-wait).

  split_batchN.py N [--parts-per-half K]   (default K 5: one part per running slot of an instance)
      writes manifest.batchNL.tsv + project_meta.batchNL.json (the L rows, u order, sidecar records
      copied unchanged from project_meta.batchN.json, so the enriched license / owner_type /
      archived / fork values are kept), parts.batchN.tsv (half, workload, part, workers, projects,
      predicted h, sha256 of the part manifest), parts.batchN.assign.tsv (workload, part, project)
      and the part manifests manifest.batchN<P>.tsv as the record. Refuses to overwrite.
  split_batchN.py --derive DIR WL
      on the instance: rebuilds DIR/manifest.<WL><P>.tsv from DIR/manifest.<WL>.tsv,
      DIR/parts.<WL>.tsv and DIR/parts.<WL>.assign.tsv and checks each sha256 against
      parts.<WL>.tsv (exit 1 if any differs), so the part manifests are byte-identical to the
      record here. Installed there as census-fed-derive.

Parts are balanced by predicted wall time (see main), and every part keeps u order. Predicted
time in seconds: exp(-5.846 + 0.5957 ln(commits) + 0.4389 ln(tok_bytes)) from frame.layer1.csv, the
fit of split_batch5.py (354 finished EC2 projects, R^2 0.73); the predictions are inferred.
The part manifests need no own sidecar: ctp census takes project_meta.batchN.json, keyed by name.
"""
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLASS_COL = 4  # name url category file_filter size_class commit
FIT = (-5.846, 0.5957, 0.4389)
WORKERS = 4


def read_manifest(path: Path):
    lines = path.read_text(encoding="utf-8").splitlines()
    cols = next(line for line in lines if line.startswith("# Columns:"))
    rows = [line for line in lines if line.strip() and not line.startswith("#")]
    return cols, rows


def name(row: str) -> str:
    return row.split("\t")[0]


def part_text(src: Path, part: str, workers: int, pred_h: str, names: set) -> str:
    """The part manifest: the rows of src named in names, in src (u) order. Used here and by --derive."""
    cols, rows = read_manifest(src)
    keep = [r for r in rows if name(r) in names]
    assert len(keep) == len(names), (src, part)
    return (f"# Part {part} of the S and M projects of {src.name} (sha256 "
            f"{hashlib.sha256(src.read_bytes()).hexdigest()}),\n"
            f"# balanced by predicted time ({pred_h} h for {workers} workers), u order; a fed spot part.\n"
            f"# {len(keep)} projects in u order.\n{cols}\n" + "".join(r + "\n" for r in keep))


def read_parts(d: Path, wl: str):
    parts = [line.split("\t") for line in (d / f"parts.{wl}.tsv").read_text(encoding="utf-8").splitlines()
             if line and not line.startswith("#")][1:]
    assign = {}
    for line in (d / f"parts.{wl}.assign.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        w, p, n = line.split("\t")
        assign.setdefault((w, p), set()).add(n)
    return parts, assign


def derive(d: Path, wl: str) -> int:
    parts, assign = read_parts(d, wl)
    bad = 0
    for half, w, p, k, n, h, sha in parts:
        assert w == wl, (w, wl)
        text = part_text(d / f"manifest.{w}.tsv", p, int(k), h, assign[(w, p)])
        got = hashlib.sha256(text.encode("utf-8")).hexdigest()
        (d / f"manifest.{w}{p}.tsv").write_text(text, encoding="utf-8")
        ok = got == sha and len(assign[(w, p)]) == int(n)
        bad += not ok
        print(f"{half} {w}{p}: {n} projects, {k} workers, sha256 {'ok' if ok else 'DIFFERS ' + got}")
    return 1 if bad else 0


def counts(rows: list) -> str:
    c = {k: sum(r.split("\t")[CLASS_COL] == k for r in rows) for k in "SML"}
    return f"S {c['S']}  M {c['M']}  L {c['L']}"


def main(n: int, per_half: int) -> None:
    wl = f"batch{n}"
    src = HERE / f"manifest.{wl}.tsv"
    names_out = [f"manifest.{wl}L.tsv", f"project_meta.{wl}L.json", f"parts.{wl}.tsv", f"parts.{wl}.assign.tsv"]
    parts = [(h, f"{h}{i}") for h in "ab" for i in range(1, per_half + 1)]
    names_out += [f"manifest.{wl}{p}.tsv" for _, p in parts]
    for f in names_out:
        assert not (HERE / f).exists(), f"{f} exists"
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    cols, rows = read_manifest(src)
    meta = json.loads((HERE / f"project_meta.{wl}.json").read_text(encoding="utf-8"))
    u = {}
    for line in (HERE / f"manifest.{wl}.order.tsv").read_text(encoding="utf-8").splitlines():
        c = line.split("\t")
        if line.startswith("#") or c[0] == "queue_pos":
            continue
        u[c[1]] = float(c[4])
    assert set(u) == {name(r) for r in rows}
    assert all(u[name(rows[i])] <= u[name(rows[i + 1])] for i in range(len(rows) - 1))
    frame = {r["repo_url"].rstrip("/").removesuffix(".git"): r
             for r in csv.DictReader(open(HERE / "frame.layer1.csv", encoding="utf-8"))}

    def pred(row: str) -> float:
        f = frame[row.split("\t")[1].rstrip("/").removesuffix(".git")]
        return math.exp(FIT[0] + FIT[1] * math.log(int(f["commits"]))
                        + FIT[2] * math.log(max(int(f["tok_bytes"] or 1), 1)))

    print(f"{wl}: {len(rows)} projects  {counts(rows)}")
    large = [r for r in rows if r.split("\t")[CLASS_COL] == "L"]
    (HERE / f"manifest.{wl}L.tsv").write_text(
        f"# The L projects of {src.name} (sha256 {sha}), for the census {wl}L on the big on-demand EC2.\n"
        f"# {len(large)} projects in u order.\n{cols}\n" + "".join(r + "\n" for r in large), encoding="utf-8")
    (HERE / f"project_meta.{wl}L.json").write_text(
        json.dumps({name(r): meta[name(r)] for r in large}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{wl}L: {len(large)} projects  {counts(large)}  predicted h: "
          + ", ".join(f"{name(r)} {pred(r) / 3600:.1f}" for r in large))

    small = [r for r in rows if r.split("\t")[CLASS_COL] != "L"]
    # Bins 0..2K-1 of 4 workers each, alternately of half a and b. Longest first, each project goes to
    # the least-loaded worker of all bins (ties: lower worker index), i.e. LPT over all 4 * 2K workers;
    # a bin's predicted wall time is that of its most-loaded worker. Then in each half the bins are
    # named by wall time, longest first: part 1 is the first one the feeder starts there.
    nb = 2 * per_half
    wload = [0.0] * (nb * WORKERS)
    load, binr = [0.0] * nb, [[] for _ in range(nb)]
    for r in sorted(small, key=lambda r: (-pred(r), u[name(r)])):
        w = min(range(nb * WORKERS), key=lambda w: (wload[w], w % nb, w))
        wload[w] += pred(r); load[w % nb] += pred(r); binr[w % nb].append(name(r))
    wall = lambda b: max(wload[w] for w in range(nb * WORKERS) if w % nb == b)
    load_, share, walls = {}, {}, {}
    for i, h in enumerate("ab"):
        mine = sorted(range(i, nb, 2), key=lambda b: (-wall(b), b))
        for k, b in enumerate(mine, 1):
            p = f"{h}{k}"
            load_[p], share[p], walls[p] = load[b], binr[b], wall(b)
    load = load_
    table, assign = [], []
    for h, p in parts:
        ph = f"{load[p] / 3600:.1f}"
        text = part_text(src, p, WORKERS, ph, set(share[p]))
        (HERE / f"manifest.{wl}{p}.tsv").write_text(text, encoding="utf-8")
        _, keep = read_manifest(HERE / f"manifest.{wl}{p}.tsv")
        assert all(u[name(keep[i])] <= u[name(keep[i + 1])] for i in range(len(keep) - 1))
        table.append((h, wl, p, str(WORKERS), str(len(keep)), ph, hashlib.sha256(text.encode("utf-8")).hexdigest()))
        assign += [(wl, p, name(r)) for r in keep]
        mx = max(pred(r) for r in keep) / 3600
        print(f"{h} {wl}{p}: {len(keep)} projects  {counts(keep)}  predicted {ph} h of work, wall "
              f"{walls[p] / 3600:.1f} h on {WORKERS} workers (longest project {mx:.1f} h)")
    assert sorted(a[2] for a in assign) == sorted(name(r) for r in small)
    (HERE / f"parts.{wl}.tsv").write_text(
        f"# Fed spot parts of {wl} (split_batchN.py {n}): the S and M projects of manifest.{wl}.tsv. sha256 is\n"
        f"# that of the part manifest manifest.<workload><part>.tsv, which split_batchN.py --derive rebuilds.\n"
        "half\tworkload\tpart\tworkers\tprojects\tpredicted_h\tsha256\n"
        + "".join("\t".join(t) + "\n" for t in table), encoding="utf-8")
    (HERE / f"parts.{wl}.assign.tsv").write_text(
        "workload\tpart\tproject\n" + "".join("\t".join(a) + "\n" for a in assign), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--derive":
        sys.exit(derive(Path(sys.argv[2]), sys.argv[3]))
    if len(sys.argv) in (2, 4) and sys.argv[1].isdigit() and int(sys.argv[1]) >= 6:
        k = 5
        if len(sys.argv) == 4:
            assert sys.argv[2] == "--parts-per-half", sys.argv[2]
            k = int(sys.argv[3])
        main(int(sys.argv[1]), k)
        sys.exit(0)
    print("usage: split_batchN.py N [--parts-per-half K] | split_batchN.py --derive DIR WL", file=sys.stderr)
    sys.exit(2)
EOF_census-fed-derive
chmod 755 /usr/local/bin/census-fed-derive.new
mv -f /usr/local/bin/census-fed-derive.new /usr/local/bin/census-fed-derive
cat > /usr/local/bin/census-fed-enqueue.new <<'EOF_census-fed-enqueue'
#!/usr/bin/env bash
# census-fed-enqueue WORKLOAD [a|b] (root): queue the fed parts of WORKLOAD (e.g. batch6) for this
# spot half (default: /etc/cregit-census/fed/half, else HALF of the census-b5 batch.env). It copies
# s3://BUCKET/WORKLOAD/input/ to /home/ec2-user/fed-input/WORKLOAD/ (sha256-checked), derives the part
# manifests with census-fed-derive (= split_batchN.py --derive; each sha256 must equal
# parts.WORKLOAD.tsv), and appends to the queue, in parts-file order, every part of the half that is
# not queued or started yet and has projects without s3://BUCKET/WORKLOAD/<part>/done/<project>/OK.
# It adds "fed" to /etc/cregit-census/censuses (read by census-spot-decide) and starts the feeder timer.
# Without /etc/cregit-census/fed/wl/WORKLOAD.env it writes one with the cregit commit "pending" (see
# census-fed-workload): the feeder then starts none of its parts until the commit is set.
# Batch 7 and later: upload its inputs, then run census-fed-enqueue batch7 on each instance.
set -euo pipefail
. /usr/local/bin/census-fed-common
WL=${1:-}; [[ $WL =~ ^batch[0-9]+$ ]] || { echo "usage: census-fed-enqueue WORKLOAD [a|b]" >&2; exit 2; }
X=${2:-$(fed_half)}; case $X in a|b) ;; *) echo "no half: give a|b" >&2; exit 2 ;; esac
mkdir -p $FED; [ -f $FED/half ] || echo $X > $FED/half
[ "$(cat $FED/half)" = $X ] || { echo "this instance is half $(cat $FED/half), not $X" >&2; exit 2; }
D=$FI/$WL; mkdir -p $D
aws s3 cp $BUCKET/$WL/input/ $D/ --recursive --only-show-errors
(cd $D && sha256sum --quiet -c SHA256SUMS) && echo "$WL inputs: sha256 ok ($(grep -c . $D/SHA256SUMS) files)"
out=$(python3 -I /usr/local/bin/census-fed-derive --derive $D $WL) || { echo "$out"; echo "DERIVE FAILED: a part manifest differs from parts.$WL.tsv"; exit 1; }
echo "$out" | grep "^$X " || true
chown -R ec2-user: $FI
exec 9>$FED/lock; flock 9
touch $FED/queue $FED/started
n=0
while read -r h wl p; do
  [ "$h" = $X ] || continue
  id=$wl$p
  if grep -qx "$wl $p" $FED/queue || grep -qx "$id" $FED/started; then echo "$id: already queued or started"; continue; fi
  left=$(comm -23 <(grep -v -e '^#' -e '^[[:space:]]*$' $D/manifest.$id.tsv | cut -f1 | sort -u) <(oks "$BUCKET/$wl/$p/done/") | grep -c . || true)
  if [ "$left" = 0 ]; then echo "$id: every project has done/OK; not queued"; continue; fi
  echo "$wl $p" >> $FED/queue; n=$((n+1)); echo "$id: queued ($left of $(nrows $D/manifest.$id.tsv) projects left)"
done < <(awk -F'\t' '!/^#/ && $1 != "half" {print $1, $2, $3}' $D/parts.$WL.tsv)
[ -f $FED/wl/$WL.env ] || /usr/local/bin/census-fed-workload $WL --pending
touch /etc/cregit-census/censuses; grep -qx fed /etc/cregit-census/censuses || echo fed >> /etc/cregit-census/censuses
chmod 644 $FED/queue $FED/started
echo "queued $n parts of $WL; queue now: $(tr '\n' ' ' < $FED/queue)"
flock -u 9
systemctl start census-fed-feeder.timer census-fed-watch.service census-fed-upload.timer census-fed-live.timer
EOF_census-fed-enqueue
chmod 755 /usr/local/bin/census-fed-enqueue.new
mv -f /usr/local/bin/census-fed-enqueue.new /usr/local/bin/census-fed-enqueue
cat > /usr/local/bin/census-fed-workload.new <<'EOF_census-fed-workload'
#!/usr/bin/env bash
# census-fed-workload WORKLOAD --pending | --base | --commit SHA --bundle S3URL --bundle-sha256 H --want-pq H [--want-srcml H]
# (root): the cregit commit of a fed workload, in /etc/cregit-census/fed/wl/WORKLOAD.env. Every fed part
# of WORKLOAD gets its own copy of /data/cregit-ec2 (95cdc88), which census-fed-part-init checks out at
# CREGIT_COMMIT (fetched from the git bundle CREGIT_BUNDLE, sha256-checked) before the part's census
# starts; census-fed-check then gates the copy against WANT_PQ (libexpat Parquet sha256) and WANT_SRCML.
#   --pending  the commit is not known yet: the feeder starts no part of WORKLOAD (it waits);
#   --base     run on the AMI cregit 95cdc88 with the batch 5 gate values (no bundle).
# --show prints the file. Changing the commit of a workload with started parts is refused.
set -euo pipefail
. /usr/local/bin/census-fed-common
WL=${1:-}; shift || true
[[ $WL =~ ^batch[0-9]+$ ]] || { echo "usage: census-fed-workload WORKLOAD --pending|--base|--show|--commit ..." >&2; exit 2; }
F=$FED/wl/$WL.env; mkdir -p $FED/wl
commit="" bundle="" bsha="" pq="" srcml=dea4467bb1b0a435e4536be13367325564b82e14ff69b478ad31bf144a8455f3
case ${1:-} in
  --show) cat $F 2>/dev/null || echo "no $F"; exit 0 ;;
  --pending) commit=pending ;;
  --base) commit=$(sudo -u ec2-user git -C /data/cregit-ec2 rev-parse HEAD); pq=40511e0de1a285b5bbc4ae0ff277e4775c5d67709966dd7c64dc9163c638fc5d ;;
  --commit) while [ $# -gt 0 ]; do case $1 in
      --commit) commit=$2; shift 2 ;; --bundle) bundle=$2; shift 2 ;; --bundle-sha256) bsha=$2; shift 2 ;;
      --want-pq) pq=$2; shift 2 ;; --want-srcml) srcml=$2; shift 2 ;; *) echo "unknown $1" >&2; exit 2 ;; esac; done
    [[ $commit =~ ^[0-9a-f]{40}$ ]] && [[ $bsha =~ ^[0-9a-f]{64}$ ]] && [[ $pq =~ ^[0-9a-f]{64}$ ]] && [ -n "$bundle" ] \
      || { echo "--commit needs a 40-hex SHA, --bundle, --bundle-sha256 and --want-pq (64-hex)" >&2; exit 2; } ;;
  *) echo "usage: census-fed-workload WORKLOAD --pending|--base|--show|--commit ..." >&2; exit 2 ;;
esac
for id in $(fed_started); do
  case $id in $WL[ab][0-9]*) [ -f $F ] && ! grep -qx "CREGIT_COMMIT=$commit" $F && { echo "$id of $WL already started with $(grep CREGIT_COMMIT $F): refusing to change the commit" >&2; exit 1; } ;; esac
done
printf 'CREGIT_COMMIT=%s\nCREGIT_BUNDLE=%s\nCREGIT_BUNDLE_SHA256=%s\nWANT_PQ=%s\nWANT_SRCML=%s\n' "$commit" "$bundle" "$bsha" "$pq" "$srcml" > $F.new
chmod 644 $F.new; mv -f $F.new $F
echo "$WL: $(tr '\n' ' ' < $F)"
EOF_census-fed-workload
chmod 755 /usr/local/bin/census-fed-workload.new
mv -f /usr/local/bin/census-fed-workload.new /usr/local/bin/census-fed-workload
cat > /usr/local/bin/census-fed-run.new <<'EOF_census-fed-run'
#!/usr/bin/env bash
# census-fed-run ID (census-fed@ID.service): one fed census part (batch 6 or later) on a spot instance,
# on its own loop XFS /w/ID with its own ctp clone, cregit copy (95cdc88) and output (see
# /etc/cregit-census/fed/ID.env). Flags of the census-b5 parts. Stop after the running projects:
# touch $CTP/STOP (census-fed-watch does it on a spot notice).
set -euo pipefail
. /etc/cregit-census/fed/$1.env
M=$IN/manifest.$ID.run.tsv
export CTP_CONFIG=$CFG
cd "$CTP"
echo "=== $(date -u +%FT%TZ) fed census $ID ($WL part $PART) start on $(cat /sys/devices/virtual/dmi/id/board_asset_tag) (cregit $(git -C "$CREGIT" rev-parse --short HEAD) at $CREGIT, want ${CREGIT_COMMIT:0:7}, ctp $(git rev-parse --short HEAD), $(grep -c -v -e '^#' -e '^[[:space:]]*$' "$M") projects, $WORKERS workers, out $OUT, floor ${FLOOR}G)"
exec .venv/bin/python ctp.py census --manifest "$M" --project-meta "$IN/project_meta.$WL.json" \
    --workers "$WORKERS" --retries 3 --skip-html --latest --tokenizer-worker \
    --blame-jobs 4 --memory-limit 16GB --min-free-mem-gb 24 --disk-floor-gb "$FLOOR"
EOF_census-fed-run
chmod 755 /usr/local/bin/census-fed-run.new
mv -f /usr/local/bin/census-fed-run.new /usr/local/bin/census-fed-run
echo "s6 files 0 installed"
