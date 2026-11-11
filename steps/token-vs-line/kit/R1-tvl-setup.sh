#!/usr/bin/env bash
# R1-tvl-setup.sh (the token-vs-line machine, root, through ssm-tvl.sh; idempotent; starts nothing):
#   - git (dnf) and Python 3.12; one XFS for each instance-store disk at /data1..N, /data -> /data1; the run uses
#     /data/tvl and needs 700 GB free (about 250 pinned clones, the TOM files, the blame outputs, the DuckDB temp);
#   - /data/tvl/venv: Python 3.12 with duckdb of tvl.conf (binary wheel only);
#   - /data/tvl/tools: the stage of S1-tvl-stage.sh from s3://B/token-vs-line/tools/ (U1); the sha256 of its
#     SHA256SUMS must be WANT_SUMS, and each file must check;
#   - the release root SHA256SUMS: its size must be ROOT_SUMS_SIZE; all 250 drawn TOM files must have a row;
#   - the fixture tests (test_tvl.py) with the venv and the machine git.
# Prints counts, versions and hashes only.
set -euo pipefail
export HOME=${HOME:-/root}
IID=${TVL_IID:-$(cat /sys/devices/virtual/dmi/id/board_asset_tag)}
case "||" in
  *"|$IID|"*) echo "ABORT: $IID is not the token-vs-line machine"; exit 1 ;; esac
B=${TVL_B:-s3://BUCKET_NAME}
X=${TVL_X:-/data/tvl}; T=$X/tools
WANT_SUMS=fcb5325676a472b076a2c825f09494ab003824db44448c4e5b9abfc6cd90afff
[ "$WANT_SUMS" != none ] || { echo "ABORT: no stage pin (S1 first)"; exit 1; }
echo "== $(date -u +%FT%TZ) $IID run ${TVL_RUN:-?} $(nproc) vCPU $(free -g | awk '/Mem:/{print $2}') GiB"
for i in $(seq 1 40); do dnf -y -q install git python3.12 python3.12-pip xfsprogs >/dev/null 2>&1 && break; echo "dnf busy, retry $i"; sleep 15; done
if ! mountpoint -q /data1; then
  DEVS=$(lsblk -d -n -o NAME,MODEL | awk '/Instance Storage/{print "/dev/"$1}' | sort)
  [ "$(echo $DEVS | wc -w)" -ge 1 ] || { echo "ABORT: no instance-store disk"; exit 1; }
  sed -i -e '\# /data #d' -e '\# /data[0-9]* #d' /etc/fstab
  k=0
  for d in $DEVS; do k=$((k+1))
    mkfs.xfs -f "$d" >/dev/null
    mkdir -p /data$k; mount -o noatime "$d" /data$k
    echo "UUID=$(blkid -s UUID -o value $d) /data$k xfs noatime,nofail 0 0" >> /etc/fstab
  done
  if [ -d /data ] && [ ! -L /data ]; then rmdir /data; fi
  ln -sfn /data1 /data
fi
avail=$(df -BG --output=avail /data1 | tail -1 | tr -dc '0-9')
[ "$avail" -ge 700 ] || { echo "ABORT: /data1 has ${avail} GB free, need 700"; exit 1; }
df -h /data[0-9]* | tail -n +2
mkdir -p $T $X/status $X/root
TP=${TOOLS_PREFIX:-token-vs-line/tools}
aws s3 cp --recursive $B/$TP/ $T/ --only-show-errors || { echo "ABORT: no $TP/ (the user runs U1-tvl-upload.sh first)"; exit 1; }
[ "$(sha256sum $T/SHA256SUMS | cut -d' ' -f1)" = $WANT_SUMS ] || { echo "ABORT: tools/SHA256SUMS is not ${WANT_SUMS:0:12} (S1 changed: stage, upload and pin again)"; exit 1; }
(cd $T && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: a tool sha256"; exit 1; }
echo "tools ok: $(wc -l < $T/SHA256SUMS) files, SHA256SUMS ${WANT_SUMS:0:12}"
conf() { awk -F= -v k="$1" '$1 == k {sub(/[ \t]*#.*/, "", $2); print $2}' $T/tvl.conf; }
DUCKDB=$(conf DUCKDB); ROOT=$(conf ROOT); SIZE=$(conf ROOT_SUMS_SIZE)
[ -x $X/venv/bin/python ] || python3.12 -m venv $X/venv
$X/venv/bin/pip install -q --disable-pip-version-check --only-binary=:all: duckdb==$DUCKDB
$X/venv/bin/python -I -B -c "import duckdb, sys; assert duckdb.__version__ == '$DUCKDB', duckdb.__version__; print('venv ok: python', sys.version.split()[0], 'duckdb', duckdb.__version__)"
$X/venv/bin/pip freeze > $X/pip-freeze.txt
aws configure set default.s3.max_concurrent_requests 32
echo "$(git --version)"
aws s3 cp $B/$ROOT/SHA256SUMS $X/root/SHA256SUMS --only-show-errors
got=$(stat -c %s $X/root/SHA256SUMS)
[ "$got" = "$SIZE" ] || { echo "ABORT: the root SHA256SUMS has $got bytes, not $SIZE"; exit 1; }
echo "root SHA256SUMS: $got bytes, sha256 $(sha256sum $X/root/SHA256SUMS | cut -d' ' -f1)"
miss=$(tail -n +2 $T/plan.tsv | awk -F'\t' '{print "parquet/"$2"-dataset.parquet"}' | while read -r f; do grep -q "  $f$" $X/root/SHA256SUMS || echo "$f"; done | wc -l)
[ "$miss" = 0 ] || { echo "ABORT: $miss drawn TOM files have no root row"; exit 1; }
grep -q "  organizations/organization_domains.parquet$" $X/root/SHA256SUMS || { echo "ABORT: no domain table row"; exit 1; }
echo "root rows ok: 250 drawn TOM files and the domain table"
(cd $(mktemp -d) && $X/venv/bin/python -I -B $T/test_tvl.py > $X/test-fixture.txt 2>&1) || { tail -15 $X/test-fixture.txt; echo "ABORT: the fixture tests"; exit 1; }
echo "fixture tests: $(tail -1 $X/test-fixture.txt) ($(grep -c ' ok$' $X/test-fixture.txt) tests)"
echo "R1-tvl done $(date -u +%FT%TZ)"
