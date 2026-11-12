#!/usr/bin/env bash
# R1-tom6-setup.sh (the TOM-6 machine, root, through ssm-tom6.sh; idempotent; starts nothing):
#   - one XFS for each instance-store disk at /data1..N, /data -> /data1; the run uses /data1 (/data/tom6); it needs
#     300 GB free (the changed TOM-4 files and their outputs are about 2 x 62 GB, the new files about 10 GB);
#   - /data/tom6/venv: Python 3.12 with pyarrow, duckdb, huggingface_hub, hf-xet and boto3 of tom6.conf (binary
#     wheels only);
#   - /data/tom6/tools: the stage of S1-tom6-stage.sh from s3://B/DEST/tools/ (U1); the sha256 of its SHA256SUMS must
#     be WANT_SUMS, and each file must check;
#   - /data/tom6/lsc: the scanner tools of the license pass for the rescan of the new projects: the stage of
#     ../license-scancode-kit in s3://B/LSC_TOOLS_PREFIX/ (its SHA256SUMS sha256 LSC_TOOLS_SUMS), the Nix closure of
#     its TOOLS_STORE_PATH, licensee gems, the template helper jar; tools.json; the versions (ScanCode 32.5.0,
#     askalono 0.5.0, licensee 10.1.0, SPDX list 3.29.0) and ScanCode once on a small file;
#   - the smoke test: a value pass of the small TOM-4 file SMOKE (license MIT -> a test value, --values) and its check;
#   - /data/tom6/duckdb-tmp: the DuckDB temp folder (the unit runs in /data/tom6, not in /).
# Prints counts, versions and hashes only.
set -euo pipefail
export HOME=${HOME:-/root}
IID=${TOM_IID:-$(cat /sys/devices/virtual/dmi/id/board_asset_tag)}
case "|REFUSED_INSTANCE_IDS|" in
  *"|$IID|"*) echo "ABORT: $IID is not the TOM-6 machine"; exit 1 ;; esac
B=${TOM_B:-s3://BUCKET_NAME}
X=${TOM_X:-/data/tom6}; T=$X/tools
WANT_SUMS=086d54a1cedb8a6d6287e17a1f5408cf3c0a3481375c057a0b98be39f297123d
SMOKE=libexpat__libexpat-dataset.parquet
[ "$WANT_SUMS" != none ] || { echo "ABORT: no stage pin (S1 first)"; exit 1; }
echo "== $(date -u +%FT%TZ) $IID run ${TOM_RUN:-?} $(nproc) vCPU $(free -g | awk '/Mem:/{print $2}') GiB"
for i in $(seq 1 40); do dnf -y -q install python3.12 python3.12-pip xfsprogs >/dev/null 2>&1 && break; echo "dnf busy, retry $i"; sleep 15; done
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
[ "$avail" -ge 300 ] || { echo "ABORT: /data1 has ${avail} GB free, need 300"; exit 1; }
df -h /data[0-9]* | tail -n +2
chown ec2-user:ec2-user /data[0-9]*
mkdir -p $T $X/status $X/duckdb-tmp $X/lsc; chown ec2-user:ec2-user $X $X/status $X/duckdb-tmp
TP=${TOOLS_PREFIX:-dataset-release/dataset-v1.1.0/tools}
aws s3 cp --recursive $B/$TP/ $T/ --only-show-errors || { echo "ABORT: no $TP/ (the user runs U1-tom6-upload.sh first)"; exit 1; }
[ "$(sha256sum $T/SHA256SUMS | cut -d' ' -f1)" = $WANT_SUMS ] || { echo "ABORT: tools/SHA256SUMS is not ${WANT_SUMS:0:12} (S1 changed: stage, upload and pin again)"; exit 1; }
(cd $T && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: a tool sha256"; exit 1; }
echo "tools ok: $(wc -l < $T/SHA256SUMS) files, SHA256SUMS ${WANT_SUMS:0:12}; $(cut -c1-400 $T/SOURCE | tr '\n' ' ')"
. $T/tom6.conf
chown -R ec2-user:ec2-user $T
AS="sudo -u ec2-user"
[ -x $X/venv/bin/python ] || $AS python3.12 -m venv $X/venv
$AS $X/venv/bin/pip install -q --disable-pip-version-check --only-binary=:all: pyarrow==$PYARROW duckdb==$DUCKDB \
  "huggingface_hub==$HF_HUB_VERSION" "hf-xet==$HF_XET_VERSION" "$BOTO3_SPEC"
$AS $X/venv/bin/python -I -B -c "import duckdb, pyarrow, huggingface_hub, hf_xet, boto3; assert (pyarrow.__version__, duckdb.__version__, huggingface_hub.__version__) == ('$PYARROW', '$DUCKDB', '$HF_HUB_VERSION'), (pyarrow.__version__, duckdb.__version__, huggingface_hub.__version__); print('venv ok', pyarrow.__version__, duckdb.__version__, huggingface_hub.__version__)"
$AS $X/venv/bin/pip freeze > $X/pip-freeze.txt
sudo -u ec2-user aws configure set default.s3.max_concurrent_requests 64
# --- the scanner tools of the license pass (the stage of ../license-scancode-kit)
LT=$X/lsc/tools-stage
mkdir -p $LT
aws s3 cp --recursive $B/$LSC_TOOLS_PREFIX/ $LT/ --only-show-errors || { echo "ABORT: no $LSC_TOOLS_PREFIX/"; exit 1; }
[ "$(sha256sum $LT/SHA256SUMS | cut -d' ' -f1)" = $LSC_TOOLS_SUMS ] || { echo "ABORT: $LSC_TOOLS_PREFIX/SHA256SUMS is not ${LSC_TOOLS_SUMS:0:12}"; exit 1; }
(cd $LT && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: a scanner tool sha256"; exit 1; }
LICENSEE_VERSION=$(sed -n 's/^LICENSEE_VERSION=//p' $LT/lsc.conf); TOOLS_STORE_PATH=$(sed -n 's/^TOOLS_STORE_PATH=//p' $LT/lsc.conf)
TOOLS_JAVA_JAR_SHA=$(sed -n 's/^TOOLS_JAVA_JAR_SHA=//p' $LT/lsc.conf)
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
if [ ! -x $TOOLS_STORE_PATH/bin/scancode ]; then
  nix --extra-experimental-features nix-command copy --no-check-sigs --from "file://$LT/nix-cache" $TOOLS_STORE_PATH
fi
nix-store --verify-path $TOOLS_STORE_PATH >/dev/null 2>&1 || nix-store --verify-path $TOOLS_STORE_PATH
E=$TOOLS_STORE_PATH/bin
mkdir -p $X/lsc/gems $X/lsc/java
[ -f $X/lsc/gems/.ok ] || { tar -C $X/lsc/gems -xzf $LT/gems/licensee-$LICENSEE_VERSION.tar.gz; touch $X/lsc/gems/.ok; }
cp -f $LT/java/tools-java-2.0.7-jar-with-dependencies.jar $LT/java/SpdxTemplateDiff.class $X/lsc/java/
[ "$(sha256sum $X/lsc/java/tools-java-2.0.7-jar-with-dependencies.jar | cut -d' ' -f1)" = $TOOLS_JAVA_JAR_SHA ] || { echo "ABORT: tools-java jar sha256"; exit 1; }
chown -R ec2-user: $X/lsc
CA=""
for f in /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt; do [ -f $f ] && { CA=$f; break; }; done
[ -n "$CA" ] || { echo "ABORT: no CA bundle"; exit 1; }
cat > $X/lsc/tools.json <<J
{"scancode": "$E/scancode", "askalono": "$E/askalono", "ruby": "$E/ruby",
 "licensee": "$X/lsc/gems/bin/licensee", "gem_home": "$X/lsc/gems",
 "java": "$E/java", "template_classpath": "$X/lsc/java:$X/lsc/java/tools-java-2.0.7-jar-with-dependencies.jar",
 "git": "$E/git", "scancode_processes": 0,
 "env": {"HOME": "/home/ec2-user", "NIX_SSL_CERT_FILE": "$CA", "GIT_SSL_CAINFO": "$CA", "LC_ALL": "C.UTF-8"}}
J
chmod 644 $X/lsc/tools.json
LAS="sudo -u ec2-user env HOME=/home/ec2-user PATH=$E:/usr/bin:/bin LC_ALL=C.UTF-8 NIX_SSL_CERT_FILE=$CA"
v_sc=$($LAS $E/scancode --version 2>/dev/null | awk '/ScanCode version/{print $3}')
v_as=$($LAS $E/askalono --version | awk '{print $2}')
v_li=$($LAS env GEM_HOME=$X/lsc/gems GEM_PATH=$X/lsc/gems $E/ruby $X/lsc/gems/bin/licensee version)
v_tj=$($LAS env SPDX_USE_ONLY_LOCAL_LICENSES=true $E/java -cp $X/lsc/java:$X/lsc/java/tools-java-2.0.7-jar-with-dependencies.jar SpdxTemplateDiff --version)
echo "scancode $v_sc, askalono $v_as, licensee $v_li, template helper $v_tj, python $($E/python3 -c 'import sys; print(sys.version.split()[0])')"
[ "$v_sc" = 32.5.0 ] && [ "$v_as" = 0.5.0 ] && [ "$v_li" = "$LICENSEE_VERSION" ] || { echo "ABORT: a scanner tool version"; exit 1; }
case "$v_tj" in *3.29.0*) ;; *) echo "ABORT: the template helper"; exit 1 ;; esac
mkdir -p $X/lsc/check; printf '%b' 'MIT License\n\nCopyright (c) 2026 Example\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\nof this software and associated documentation files (the "Software"), to deal\nin the Software without restriction, including without limitation the rights\nto use, copy, modify, merge, publish, distribute, sublicense, and/or sell\ncopies of the Software, and to permit persons to whom the Software is\nfurnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in all\ncopies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\nIMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\nFITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\nAUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\nLIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\nOUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\nSOFTWARE.\n' > $X/lsc/check/LICENSE
chown -R ec2-user: $X/lsc/check
$LAS $E/scancode -l -n 0 --quiet --json $X/lsc/check.json $X/lsc/check
$E/python3 -c "import json,sys; d=json.load(open(sys.argv[1])); r=[f.get('detected_license_expression_spdx') for f in d['files'] if f['type']=='file']; print('scancode check:', r); sys.exit(0 if r == ['MIT'] else 1)" $X/lsc/check.json
$LAS $E/python3 -I -B -c "import sys; sys.path.insert(0, '$T/inputs/lsc'); import license_scan, license_rules; print('license_scan imports ok')"
# --- the smoke test: a value pass of one small TOM-4 file
SM=$(mktemp -d -p $X); chown ec2-user:ec2-user $SM
want_in=$(awk -v f="parquet/$SMOKE" '$2 == f {print $1}' $T/inputs/tom4.SHA256SUMS)
$AS aws s3 cp $B/$TOM4_ROOT/parquet/$SMOKE $SM/in.parquet --only-show-errors
[ "$(sha256sum $SM/in.parquet | cut -d' ' -f1)" = "$want_in" ] || { echo "ABORT: the smoke input is not its TOM-4 row"; exit 1; }
old=$($AS $X/venv/bin/python -I -B -c "import duckdb; print(duckdb.sql(\"SELECT DISTINCT license FROM read_parquet('$SM/in.parquet')\").fetchall()[0][0])")
printf '%s\tlicense\t%s\tsmoke-test-value\n' $SM/in.parquet "$old" > $SM/values.tsv; chown ec2-user: $SM/values.tsv
$AS mkdir -p $SM/v
$AS $X/venv/bin/python -I -B $T/parquet_rename.py --values $SM/values.tsv --out-dir $SM/v --copy $COPY_MODE > $SM/value.json || { echo "ABORT: the value smoke: $(cut -c1-300 $SM/value.json)"; exit 1; }
$AS $X/venv/bin/python -I -B $T/parquet_rename_check.py --values $SM/values.tsv --out-dir $SM/v > $SM/vcheck.json || { echo "ABORT: the value smoke check: $(cut -c1-400 $SM/vcheck.json)"; exit 1; }
$AS $X/venv/bin/python -I -B -c "import duckdb; r = duckdb.sql(\"SELECT DISTINCT license FROM read_parquet('$SM/v/in.parquet')\").fetchall(); assert r == [('smoke-test-value',)], r; print('value smoke test ok: license $old -> smoke-test-value, check ok')"
rm -rf $SM
echo "R1-tom6 done $(date -u +%FT%TZ)"
