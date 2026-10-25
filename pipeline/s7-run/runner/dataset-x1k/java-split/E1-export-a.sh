#!/usr/bin/env bash
# E1-export-a.sh, machine A (root, through scripts/a/ssm-a.sh; made by render.sh from src/E1-export-a.body).
# The input of the aws-sdk-java split, read-only for the row (it writes only under
# /data/x1k-long/java-split/e1 on /data1 and to S3):
#   1. the running step 7: the blameRepoFiles.pl process of the row (its argv: jobs, formatBlame,
#      repo, out dir, mask), a formatBlame.pl and a git blame process (the git and perl binaries),
#      and the environment of the blame (PATH HOME LANG LC_* PERL5LIB TZ CREGIT_* GIT_*);
#   2. checks: cregit tree at 57551d7 and clean, formatBlame.pl and blameRepoFiles.pl are the
#      57551d7 blobs; working clone HEAD, clean, no alternates;
#   3. the files left in the order of blameRepoFiles.pl (jv_order.pl, a copy of its lines 65-118);
#      machine A's newest started index (jv_split.py apos, from the "<n>: <name>" lines);
#   4. the split: head = index <= apos + HEAD_FILES (A keeps it), part k = every N-th file of the
#      rest (jv_split.py split + check); the gate: GATE_N files that A finished on this machine
#      (not PLAIN-BLAME), with A's .blame files (for the gate only);
#   5. upload to s3://B/dataset-x1k/java-split/input/: clone.tar.zst (tar of the working clone,
#      zstd, streamed: no copy on A's disks), cregit.tar.zst, settings.env, blame.env, mask.txt,
#      gitconfig.txt, left.tsv, parts/, gate/, and SHA256SUMS last; then a size read-back.
# Env: N (4), HEAD_FILES (3000), GATE_N (30), MAX_CLONE_GB (400), FORCE=1 to replace an input.
# Output: counts and sizes only (no file names); each at sign is dropped.
set -uo pipefail
# Test hooks (test/t_e1s1.py only): X1K_ASSET, ROOT, JV_PROC, JV_BUCKET, JV_SUDO, SYSTEMCTL, JV_DATA1,
# JV_TEST (no chown). JV_SUDO is split into words on purpose (a command prefix).
IID=$(cat "${X1K_ASSET:-/sys/devices/virtual/dmi/id/board_asset_tag}")
PROC=${JV_PROC:-/proc}; SU=${JV_SUDO-sudo -u ec2-user}; SYSTEMCTL=${SYSTEMCTL:-systemctl}; DATA1=${JV_DATA1:-/data1}
own() { [ -n "${JV_TEST:-}" ] || chown -R ec2-user: "$@"; }
[ "$IID" = ${RUNNER_EC2_X1K_LONG_A4} ] || { echo "ABORT: $IID is not machine A"; exit 1; }
P=aws__aws-sdk-java
L=${ROOT:-/data/x1k-long}
X=$L/java-split/e1
B=${JV_BUCKET:-s3://${RUNNER_BUCKET}}
IN=$B/dataset-x1k/java-split/input
N=${N:-4}; HEAD_FILES=${HEAD_FILES:-3000}; GATE_N=${GATE_N:-30}; MAX_CLONE_GB=${MAX_CLONE_GB:-400}
CREGIT_COMMIT=57551d7ad82a784615c1490623d72cb9dc994ba1
FB_BLOB=76d8a379d47ad87ac13b2ca28cf6985d4ff94824
BRF_BLOB=7036ef5ab963a4a5a7fc78572615e415ab8114ef
for v in N HEAD_FILES GATE_N MAX_CLONE_GB; do case ${!v} in ''|*[!0-9]*) echo "ABORT: $v is not a whole number"; exit 1 ;; esac; done
[ "$N" -ge 1 ] && [ "$N" -le 20 ] || { echo "ABORT: N=$N"; exit 1; }

main() {
echo "== $(date -u +%FT%TZ) E1 on $IID: N=$N HEAD_FILES=$HEAD_FILES GATE_N=$GATE_N"
T=$(readlink -f $L/$P); W=$T/out/$P/$P-cregit; PL=$T/out/$P/pipeline.log
if aws s3 ls "$IN/SHA256SUMS" > /dev/null 2>&1 && [ "${FORCE:-0}" != 1 ]; then
  echo "ABORT: $IN/SHA256SUMS exists (an earlier E1). FORCE=1 replaces it; do that only before any extra starts"; return 1
fi
if aws s3 ls "$B/dataset-x1k/java-split/out/" > /dev/null 2>&1; then
  echo "ABORT: java-split/out/ has files: extras ran with the old input. Do not replace it"; return 1
fi
$SYSTEMCTL is-active -q "x1k-long@$P" || { echo "ABORT: x1k-long@$P is not active"; return 1; }
st=$(grep -a -E '^  Step [0-9]+ ' "$PL" | tail -1 | awk '{print $2}')
[ "$st" = 7 ] || { echo "ABORT: the newest step heading is $st, not 7"; return 1; }

# 1. the running step 7
local brf="" fbp="" gp="" d a
for d in "$PROC"/[0-9]*; do
  a=$(tr '\0' '\n' < "$d/cmdline" 2>/dev/null) || continue
  case "$a" in
    *blameRepoFiles.pl*) echo "$a" | grep -q -x -F "$W" && brf=${d#"$PROC"/} ;;
    *formatBlame.pl*) [ -z "$fbp" ] && echo "$a" | grep -q -x -F "$W" && fbp=${d#"$PROC"/} ;;
  esac
  if [ -z "$gp" ] && echo "$a" | grep -q -x blame && echo "$a" | grep -q -x -F "$W"; then
    case $(readlink "$d/exe" 2>/dev/null | sed 's#.*/##') in git|.git-wrapped|git-*) gp=${d#"$PROC"/} ;; esac
  fi
done
[ -n "$brf" ] || { echo "ABORT: no blameRepoFiles.pl process with the repo $W"; return 1; }
[ -n "$gp" ] || { echo "ABORT: no git blame process of the row"; return 1; }
mapfile -t ARGV < <(tr '\0' '\n' < "$PROC/$brf/cmdline")
local na=${#ARGV[@]} jobs="" fb="" repo out mask
repo=${ARGV[$((na - 3))]}; out=${ARGV[$((na - 2))]}; mask=${ARGV[$((na - 1))]}
for a in "${ARGV[@]}"; do case $a in --jobs=*) jobs=${a#--jobs=} ;; --formatBlame=*|--formatblame=*) fb=${a#*=} ;; --overwrite) echo "ABORT: the run has --overwrite"; return 1 ;; esac; done
[ "$repo" = "$W" ] || { echo "ABORT: the repo argument is not $W"; return 1; }
[ "$out" = "$T/out/$P/blame" ] || { echo "ABORT: the out argument is not $T/out/$P/blame"; return 1; }
[ -n "$fb" ] && [ -f "$fb" ] || { echo "ABORT: no formatBlame path in the argv"; return 1; }
local C GITEXE PERLEXE envp
C=$(cd "$(dirname "$fb")/.." && pwd)
GITEXE=$(readlink -f "$PROC/$gp/exe"); PERLEXE=$(readlink -f "$PROC/$brf/exe")
envp=$brf; [ -n "$fbp" ] && envp=$fbp
mkdir -p "$X"; rm -rf "$X/parts" "$X/gate"; mkdir -p "$X/parts" "$X/gate/a" "$X/bin"
tr '\0' '\n' < "$PROC/$envp/environ" | grep -E '^(PATH|HOME|LANG|LC_[A-Z]+|PERL5LIB|TZ|CREGIT_[A-Z0-9_]+|GIT_[A-Z0-9_]+)=' > "$X/blame.env"
printf '%s\n' "$mask" > "$X/mask.txt"
echo "step 7 process $brf: jobs $jobs; env from $( [ -n "$fbp" ] && echo formatBlame.pl || echo blameRepoFiles.pl ): $(cut -d= -f1 "$X/blame.env" | tr '\n' ' ')"
echo "  CREGIT_C100_LIMIT: $(sed -n 's/^CREGIT_C100_LIMIT=//p' "$X/blame.env" | grep . || echo 'not set (3600 s)')"
echo "  git $GITEXE: $("$GITEXE" --version); perl $PERLEXE: $("$PERLEXE" -e 'print $^V')"

# 2. checks
[ "$($SU git -C "$C" rev-parse HEAD)" = $CREGIT_COMMIT ] || { echo "ABORT: cregit $C is not at 57551d7"; return 1; }
[ -z "$($SU env GIT_OPTIONAL_LOCKS=0 git -C "$C" status --porcelain --untracked-files=no)" ] || { echo "ABORT: cregit $C is dirty"; return 1; }
[ "$($SU git hash-object "$C/blameRepo/formatBlame.pl")" = $FB_BLOB ] || { echo "ABORT: formatBlame.pl is not the 57551d7 blob"; return 1; }
[ "$($SU git hash-object "$C/blameRepo/blameRepoFiles.pl")" = $BRF_BLOB ] || { echo "ABORT: blameRepoFiles.pl is not the 57551d7 blob"; return 1; }
local RHEAD
RHEAD=$($SU git -C "$W" rev-parse HEAD) || { echo "ABORT: no HEAD in the working clone"; return 1; }
[ -z "$($SU env GIT_OPTIONAL_LOCKS=0 git -C "$W" status --porcelain --untracked-files=no | head -1)" ] || { echo "ABORT: the working clone is not clean"; return 1; }
[ ! -e "$W/.git/objects/info/alternates" ] || { echo "ABORT: the working clone has alternates"; return 1; }
$SU git -C "$W" config --list --show-scope 2>/dev/null | grep -v -E '^[a-z]+[[:space:]]+(user|credential|sendemail|safe)\.' | sed 's/@//g' > "$X/gitconfig.txt"
local CB
CB=$(du -sb "$W" | cut -f1)
echo "cregit $C at 57551d7, clean, blobs ok; working clone HEAD ${RHEAD:0:12}, clean, no alternates, $((CB / 1000000)) MB"
[ "$CB" -le $((MAX_CLONE_GB * 1000000000)) ] || { echo "ABORT: the working clone is over $MAX_CLONE_GB GB"; return 1; }

# 3. the order
# embedded lib/jv_order.pl (sha256 7251766e0ab93f94)
mkdir -p "$(dirname "$X/bin/jv_order.pl")"
base64 -d <<'EOF_JV_EMBED' | gunzip > "$X/bin/jv_order.pl.tmp"
H4sIAAAAAAAC/5VVW2/aSBR+51eculQYhUuomk0FASVd2KqqdqkIuy/bKhrsAWYxM9bMOCFN+O97
zgw2dhJVrR/suZz5zncu8/n1q25mdHchZJfLW0i5Tmqv4b/bG6VjrjtpArPJlylM/56PP83gz6vr
zzCe/jW5wQUItyxaC8nhqgXMAI/etjPD9QA0Z3FbyeS+2UGw+ZrDUiQcEmEsqCUsErblM56qP3DV
kA9cjDRfCQtn52dnvfgcwgSBDfx21u713jdbcCfsGqTyZ3PUSMUcFjxRdyAMMJyn94Rl18qQO0To
Q5owIYGwE9MmHgZCBGp/R1SLIFtmNkSfwRcfPBLhO7/XRl5rHm2Mn5qNSP0CeWES+A5DEnIFHccL
0yBjb6m0hdCI7xxibiJ3XCJ2QcGlt9mBa+Xs3ZSCOE5cHBx0JiV5MJancE6RX9tYZbYPgZAx313M
rz6MyJEbSGQRwFJp4FibQ9r5Erk4Y+jB0KEuhcZauO2jH1etvLqI/0NUu2YW1i5vPvgOEeNa9x1c
pDJpTaeGDYHUtYjswI3vmKZwzKBWiwWHIDNsxfs/13BfZQCZxOwZMBFLmA4vr2Yf/2nCcAjvBrXt
PYR1jW01FroFdcxRmlk/JsYzvprsUprFSvJpZvEcOAB3tO6CmOwsl0YoiXuBjytAqirlMiQjV7wW
NNqPDXxjU9Gn/Tu+j54beZEbzRrgg2nzoUq2oMRhxTW75RqzQV1J5+Df/Pg3qL8KHKFLtIo2PHaX
BOlceOejQS1KsL1DP23+IjxFQ4FsmcVGjhH31IfPErq192PMTbF46VzM1QfKg1+h3CEE9oJrhbDC
sgkPLuJorbbpwA3FEsJy+gHhgyA3pEfync3L2i2bdj3C3r2JIrUhcqvfDIolpcVKSJaQe9o6hAkd
CLoBvt2Zkrnridy46JCqOX2rzeABykRRGCq+n1uET01gBKdNb5dn/+TkmCRnXtArJ6hcmvwEPWlm
1r4grXKcOZFy9rxpuZrFkX3tIKZOsl5U597pO1LhPuCVW3GnG6geqGkCG3PDUZfoxlelrUPd8oYU
ZLocFO1SVDGskMmjrXv7B2ezxxK1DQR5Tbt1L0OPj9Sde9e0omjVN140hyjnKTxgj8BwhPsnJ7B/
2saVKZ5wgT8hsNjDBQHkc7Yvcqu0N3UOacdbHqaLfe2ZQ0dVeqo/mwmZVzrVQlrMgvxqq+nBOX1R
FCkbhULFKECjRlnlngvEnRaWoygcTL71vei8wI0sck60bH5YlCPfeow2pkrxIFvxS4zc3nNGHux6
Pp7MZhAcpAbopuY/gKr84D32//NC3wiwKm7ud1iGqOYfIRzf/wHPDi6bGQkAAA==
EOF_JV_EMBED
[ "$(sha256sum < "$X/bin/jv_order.pl.tmp" | cut -d" " -f1)" = 7251766e0ab93f941ca5bccc96b4cae3e21e1fea70ad8d7840e42dfe66ce231f ] || { echo "ABORT: embedded lib/jv_order.pl sha256"; exit 1; }
chmod 755 "$X/bin/jv_order.pl.tmp" && mv -f "$X/bin/jv_order.pl.tmp" "$X/bin/jv_order.pl"
# embedded lib/jv_split.py (sha256 d1f77176edafbd61)
mkdir -p "$(dirname "$X/bin/jv_split.py")"
base64 -d <<'EOF_JV_EMBED' | gunzip > "$X/bin/jv_split.py.tmp"
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
nFpRXGExfTWZokL+B+eSGladIQAA
EOF_JV_EMBED
[ "$(sha256sum < "$X/bin/jv_split.py.tmp" | cut -d" " -f1)" = d1f77176edafbd616d615dc86af0105fd113199a573ee87bf149c18a910cfff5 ] || { echo "ABORT: embedded lib/jv_split.py sha256"; exit 1; }
chmod 755 "$X/bin/jv_split.py.tmp" && mv -f "$X/bin/jv_split.py.tmp" "$X/bin/jv_split.py"
own "$X"
# root writes the two output files (X is on /data1); ec2-user reads the repo.
# shellcheck disable=SC2024,SC2086
# With the environment of the running blame: the same git (ls-files) and perl as blameRepoFiles.pl.
local OENV
mapfile -t OENV < "$X/blame.env"
$SU env -i "${OENV[@]}" perl "$X/bin/jv_order.pl" "$W" "$out" "$mask" "$X/done.tsv" > "$X/left.tsv.tmp" 2> "$X/order.err" \
  || { echo "ABORT: jv_order.pl failed: $(tail -1 "$X/order.err")"; return 1; }
mv -f "$X/left.tsv.tmp" "$X/left.tsv"
echo "order: $(tail -1 "$X/order.err")"
local APOS
APOS=$(python3 -I "$X/bin/jv_split.py" apos --left "$X/left.tsv" --log "$PL") || { echo "ABORT: apos"; return 1; }
echo "machine A newest started index: $APOS of $(wc -l < "$X/left.tsv") left"
[ "$APOS" -ge 1 ] || { echo "ABORT: no started file of the left list in pipeline.log"; return 1; }

# 4. split and gate
python3 -I "$X/bin/jv_split.py" split --left "$X/left.tsv" --apos "$APOS" --head "$HEAD_FILES" --n "$N" --out "$X/parts" \
  | sed 's/^/  /' || true
python3 -I "$X/bin/jv_split.py" check --left "$X/left.tsv" --out "$X/parts" --n "$N" | grep -q '^check: OK' \
  || { echo "ABORT: the split check failed"; return 1; }
local boot
boot=$(awk '/^btime/ {print $2}' "$PROC/stat")
python3 -I "$X/bin/jv_split.py" gate --done "$X/done.tsv" --blame-dir "$out" --log "$PL" --since "$boot" --count "$GATE_N" --out "$X/gate/gate.tsv" \
  | sed 's/^/  /'
[ "$(wc -l < "$X/gate/gate.tsv")" = "$GATE_N" ] || { echo "ABORT: the gate list"; return 1; }
# Sizes only, no names. The gate takes as long as its slowest file on the extra.
echo "  gate sizes (B): $(cut -f1 "$X/gate/gate.tsv" | tr '\n' ' ')"
local name
while IFS=$'\t' read -r _ name; do
  mkdir -p "$(dirname "$X/gate/a/$name.blame")"; cp -p "$out/$name.blame" "$X/gate/a/$name.blame" || { echo "ABORT: gate copy"; return 1; }
done < "$X/gate/gate.tsv"
{ echo "P=$P"; echo "A_IID=$IID"; echo "E1_TIME=$(date -u +%FT%TZ)"; echo "REPO=$W"; echo "OUTDIR=$out"
  echo "CREGIT_DIR=$C"; echo "CREGIT_COMMIT=$CREGIT_COMMIT"; echo "FB_BLOB=$FB_BLOB"; echo "BRF_BLOB=$BRF_BLOB"
  echo "A_JOBS=$jobs"; echo "GIT_EXE=$GITEXE"; echo "GIT_VERSION=$("$GITEXE" --version)"; echo "PERL_EXE=$PERLEXE"
  echo "PERL_VERSION=$("$PERLEXE" -e 'print $^V')"; echo "REPO_HEAD=$RHEAD"; echo "CLONE_BYTES=$CB"; echo "APOS0=$APOS"
  echo "HEAD_FILES=$HEAD_FILES"; echo "N=$N"; echo "LEFT=$(wc -l < "$X/left.tsv")"; echo "GATE_N=$GATE_N"; } > "$X/settings.env"
own "$X"

# 5. pack and upload
local CBASE free
CBASE=$(basename "$C")
free=$(df -B1 --output=avail "$DATA1" | tail -1)
[ "$free" -gt 10000000000 ] || { echo "ABORT: /data1 has less than 10 GB free"; return 1; }
tar -C "$(dirname "$C")" -cf - --exclude="$CBASE/tokenizeByBlobId/build" --exclude="$CBASE/blameRepo/build" "$CBASE" \
  | nice -n 10 zstd -q -T8 -3 -o "$X/cregit.tar.zst" -f
local prc=("${PIPESTATUS[@]}")
[ "${prc[0]}" = 0 ] && [ "${prc[1]}" = 0 ] || { echo "ABORT: cregit tar"; return 1; }
echo "cregit.tar.zst: $(( $(stat -c %s "$X/cregit.tar.zst") / 1000000 )) MB"
local F1 F2 F3 t0
F1=$X/clone.sha.fifo; F2=$X/clone.wc.fifo; rm -f "$F1" "$F2"; mkfifo "$F1" "$F2"
sha256sum < "$F1" | cut -d' ' -f1 > "$X/clone.sha256" & local s1=$!
wc -c < "$F2" > "$X/clone.bytes" & local s2=$!
t0=$(date +%s)
tar -C "$(dirname "$W")" -cf - "$(basename "$W")" | nice -n 10 zstd -q -T12 -3 -c | tee "$F1" "$F2" \
  | aws s3 cp - "$IN/clone.tar.zst" --expected-size "$CB" --only-show-errors
prc=("${PIPESTATUS[@]}")
wait $s1 $s2; rm -f "$F1" "$F2"
[ "${prc[0]}" = 0 ] && [ "${prc[1]}" = 0 ] && [ "${prc[2]}" = 0 ] && [ "${prc[3]}" = 0 ] \
  || { echo "ABORT: clone tar/zstd/upload rc ${prc[*]}"; return 1; }
F3=$(cat "$X/clone.bytes")
echo "clone.tar.zst: $((F3 / 1000000)) MB in $(( $(date +%s) - t0 )) s"
echo "CLONE_ZST_BYTES=$F3" >> "$X/settings.env"
(cd "$X" && { echo "$(cat clone.sha256)  clone.tar.zst"
  find cregit.tar.zst settings.env blame.env mask.txt gitconfig.txt left.tsv parts gate -type f -print0 | sort -z | xargs -0 sha256sum; }) > "$X/SHA256SUMS"
local f
while IFS= read -r f; do
  [ "$f" = clone.tar.zst ] && continue
  aws s3 cp "$X/$f" "$IN/$f" --only-show-errors || { echo "ABORT: upload of an input file"; return 1; }
done < <(sed 's/^[0-9a-f]*  //' "$X/SHA256SUMS")
aws s3 cp "$X/SHA256SUMS" "$IN/SHA256SUMS" --only-show-errors || { echo "ABORT: SHA256SUMS upload"; return 1; }
# read-back: every key and size
aws s3 ls --recursive "$IN/" > "$X/readback.txt"
local bad=0 sz want
while IFS= read -r f; do
  if [ "$f" = clone.tar.zst ]; then want=$F3; else want=$(stat -c %s "$X/$f"); fi
  sz=$(awk -v k="dataset-x1k/java-split/input/$f" '{n = $0; sub(/^[^ ]+ +[^ ]+ +[0-9]+ /, "", n)} n == k {print $3}' "$X/readback.txt")
  [ "$sz" = "$want" ] || bad=$((bad + 1))
done < <(sed 's/^[0-9a-f]*  //' "$X/SHA256SUMS"; echo SHA256SUMS)
[ $bad = 0 ] || { echo "ABORT: $bad input files have a wrong size in S3"; return 1; }
echo "read-back: $(($(wc -l < "$X/SHA256SUMS") + 1)) files, sizes equal"
local need
need=$(( (CB + 15000000000) / 1000000000 * 13 / 10 + 40 ))
echo "root disk of an extra: the clone needs $((CB / 1000000000)) GB unpacked; use ROOT_GB >= $need in L1 (the template has 200)"
echo "E1 done $(date -u +%FT%TZ)"
}

main 2>&1 | sed -u 's/@//g'
exit "${PIPESTATUS[0]}"
