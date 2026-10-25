#!/usr/bin/env bash
# E1-export-a.sh, machine A (root, through scripts/a/ssm-a.sh; made by render.sh from src/E1-export-a.body).
# The input of the aws-sdk-rust split, read-only for the row (it writes only under
# /data/x1k-long/rust-split/e1 on /data1 and to S3):
#   1. the running step 7: the blameRepoFiles.pl process of the row (its argv: jobs, formatBlame,
#      repo, out dir, mask), a formatBlame.pl and a git blame process (the git and perl binaries),
#      and the environment of the blame (PATH HOME LANG LC_* PERL5LIB TZ CREGIT_* GIT_*);
#   2. checks: cregit tree at 57551d7 and clean, formatBlame.pl and blameRepoFiles.pl are the
#      57551d7 blobs; working clone HEAD, clean, no alternates;
#   3. the files left in the order of blameRepoFiles.pl (rs_order.pl, a copy of its lines 65-118);
#      machine A's newest started index (rs_split.py apos, from the "<n>: <name>" lines);
#   4. the split: head = index <= apos + HEAD_FILES (A keeps it), part k = every N-th file of the
#      rest (rs_split.py split + check); the gate: GATE_N files that A finished on this machine
#      (not PLAIN-BLAME), with A's .blame files (for the gate only);
#   5. upload to s3://B/dataset-x1k/rust-split/input/: clone.tar.zst (tar of the working clone,
#      zstd, streamed: no copy on A's disks), cregit.tar.zst, settings.env, blame.env, mask.txt,
#      gitconfig.txt, left.tsv, parts/, gate/, and SHA256SUMS last; then a size read-back.
# Env: N (5), HEAD_FILES (1500), GATE_N (30), MAX_CLONE_GB (400), FORCE=1 to replace an input.
# Output: counts and sizes only (no file names); each at sign is dropped.
set -uo pipefail
# Test hooks (test/t_e1s1.py only): X1K_ASSET, ROOT, RS_PROC, RS_BUCKET, RS_SUDO, SYSTEMCTL, RS_DATA1,
# RS_TEST (no chown). RS_SUDO is split into words on purpose (a command prefix).
IID=$(cat "${X1K_ASSET:-/sys/devices/virtual/dmi/id/board_asset_tag}")
PROC=${RS_PROC:-/proc}; SU=${RS_SUDO-sudo -u ec2-user}; SYSTEMCTL=${SYSTEMCTL:-systemctl}; DATA1=${RS_DATA1:-/data1}
own() { [ -n "${RS_TEST:-}" ] || chown -R ec2-user: "$@"; }
[ "$IID" = ${RUNNER_EC2_X1K_LONG_A4} ] || { echo "ABORT: $IID is not machine A"; exit 1; }
P=awslabs__aws-sdk-rust
L=${ROOT:-/data/x1k-long}
X=$L/rust-split/e1
B=${RS_BUCKET:-s3://${RUNNER_BUCKET}}
IN=$B/dataset-x1k/rust-split/input
N=${N:-5}; HEAD_FILES=${HEAD_FILES:-1500}; GATE_N=${GATE_N:-30}; MAX_CLONE_GB=${MAX_CLONE_GB:-400}
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
if aws s3 ls "$B/dataset-x1k/rust-split/out/" > /dev/null 2>&1; then
  echo "ABORT: rust-split/out/ has files: extras ran with the old input. Do not replace it"; return 1
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
# embedded lib/rs_order.pl (sha256 3f11df69896d713b)
mkdir -p "$(dirname "$X/bin/rs_order.pl")"
base64 -d <<'EOF_RS_EMBED' | gunzip > "$X/bin/rs_order.pl.tmp"
H4sIAAAAAAAC/5VVW2/bNhR+9684VV1YRnyJh2YZ7NhIWnvDMGwuHG8vaxHQEm0RlkmBpBqnif/7
ziEtWUqCotODxMvhd75z4ae3b/q50f2VkH0uv0LGddp4C9rcKR1z3ctSWMw+zWH+93L6+wL+vLn9
A6bzv2Z3uADhjkWJkBxuOsAM8Oinbm64HoHmLO4qmT60ewi2TDisRcohFcaCWsMqZTu+4Jn6FVcN
+cDFSPONsHBxeXExiC8hTBHYwM8X3cHgl3YH7oVNQCp/tkCNVMxhxVN1D8IAw3n2QFg2UYbcIcIQ
spQJCYSdmi7xMBAiUPcboloE2TGzJfoMPh2D5xu+93td5JXwaGv81GxF5hfIC5PA9xiSkBvoOV6Y
Bhl7S6UthEZ84xBzE7njErFLCi697R7cKmfvphTEaeLi4KBzKcmDsTyDS4r81sYqt0MIhIz5/mp5
82FCjtxAIosA1koDx9oc087XyMUZwwDGDnUtNNbCbZ/8uGoV1UX876LahFlIXN588D0ixrUeOrhI
5dKaXgMbAqlrEdmRG98zTeGYUaMRCw5BbtiGD3+s4T7LAHKJ2TNgIpYyHV7fLH77pw3jMbwfNXYP
EDY1ttVU6A40MUdZbv2YGC/4ZrbPaBYryee5xXPgANzRpgtitrdcGqEk7gU+rgCpqozLkIxc8TrQ
6j618I1NRZ/uR3yfPLeKIrfaDcAH0+ZDlWxFicOKa/aVa8wGdSWdg3+L41+g+SZwhK7RKtry2F0S
pHPlnU9GjSjF9g79tP0/4SkaCmTHLDZyjLjnPnyW0q19mGJuysVr52KpPlAe/ArlDiGwF1wrhDWW
bXh0EUeJ2mUjNxRrCKvpB4QPgsKQHsn3tihrv2ra9wgH9yaK1IbIrXk3KpeUFhshWUruaesYJvQg
6Af4dmcq5q4nCuOyQ+rm9K03gweoEkVhqPl+aRE+N4EJnLe9XZH9s7NTkpx5Sa+aoGppihP0ZLlJ
fEE61TgLItXsedNqNcsjh8ZRTJ1kvarOg/P3pMJDwCu34U43UD1Q0wQ25pajLtGNr0tbj7rlHSnI
fD0q26WsYlgjU0Tb9PaPzuaAJeoaCIqa9ptehp6eqDsPrmlF2arvvGiOUc4zeMQegfEE98/O4PC8
jWtTPOECf0ZgdYArAijm7FDmVmlv6hzSjrc8TleHxguHjqr0VH80E7KodKaFtJgF+dnW04Nz+qIo
UjZKhYpRgCatqsq9FIh7LSxHUTiafBl60XmFG1kUnGjZfLcoJ77NGG1MneJRtuLXGLm9l4w82O1y
OlssIDhKDdBNLX4AdfnBe+z/56W+EWBd3NzvsApRzz9COL7/Ab+5zy8ZCQAA
EOF_RS_EMBED
[ "$(sha256sum < "$X/bin/rs_order.pl.tmp" | cut -d" " -f1)" = 3f11df69896d713ba346d1cf7c08ae2cf968001155e2111c7230456e29796c7e ] || { echo "ABORT: embedded lib/rs_order.pl sha256"; exit 1; }
chmod 755 "$X/bin/rs_order.pl.tmp" && mv -f "$X/bin/rs_order.pl.tmp" "$X/bin/rs_order.pl"
# embedded lib/rs_split.py (sha256 6552f7b4ee79233d)
mkdir -p "$(dirname "$X/bin/rs_split.py")"
base64 -d <<'EOF_RS_EMBED' | gunzip > "$X/bin/rs_split.py.tmp"
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
akVxhcX09WSKCvkfoLkIW50hAAA=
EOF_RS_EMBED
[ "$(sha256sum < "$X/bin/rs_split.py.tmp" | cut -d" " -f1)" = 6552f7b4ee79233d3aca97be43dd416d9f701af6ff35cbbc60eee0244da4e6b0 ] || { echo "ABORT: embedded lib/rs_split.py sha256"; exit 1; }
chmod 755 "$X/bin/rs_split.py.tmp" && mv -f "$X/bin/rs_split.py.tmp" "$X/bin/rs_split.py"
own "$X"
# root writes the two output files (X is on /data1); ec2-user reads the repo.
# shellcheck disable=SC2024,SC2086
# With the environment of the running blame: the same git (ls-files) and perl as blameRepoFiles.pl.
local OENV
mapfile -t OENV < "$X/blame.env"
$SU env -i "${OENV[@]}" perl "$X/bin/rs_order.pl" "$W" "$out" "$mask" "$X/done.tsv" > "$X/left.tsv.tmp" 2> "$X/order.err" \
  || { echo "ABORT: rs_order.pl failed: $(tail -1 "$X/order.err")"; return 1; }
mv -f "$X/left.tsv.tmp" "$X/left.tsv"
echo "order: $(tail -1 "$X/order.err")"
local APOS
APOS=$(python3 -I "$X/bin/rs_split.py" apos --left "$X/left.tsv" --log "$PL") || { echo "ABORT: apos"; return 1; }
echo "machine A newest started index: $APOS of $(wc -l < "$X/left.tsv") left"
[ "$APOS" -ge 1 ] || { echo "ABORT: no started file of the left list in pipeline.log"; return 1; }

# 4. split and gate
python3 -I "$X/bin/rs_split.py" split --left "$X/left.tsv" --apos "$APOS" --head "$HEAD_FILES" --n "$N" --out "$X/parts" \
  | sed 's/^/  /' || true
python3 -I "$X/bin/rs_split.py" check --left "$X/left.tsv" --out "$X/parts" --n "$N" | grep -q '^check: OK' \
  || { echo "ABORT: the split check failed"; return 1; }
local boot
boot=$(awk '/^btime/ {print $2}' "$PROC/stat")
python3 -I "$X/bin/rs_split.py" gate --done "$X/done.tsv" --blame-dir "$out" --log "$PL" --since "$boot" --count "$GATE_N" --out "$X/gate/gate.tsv" \
  | sed 's/^/  /'
[ "$(wc -l < "$X/gate/gate.tsv")" = "$GATE_N" ] || { echo "ABORT: the gate list"; return 1; }
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
  sz=$(awk -v k="dataset-x1k/rust-split/input/$f" '{n = $0; sub(/^[^ ]+ +[^ ]+ +[0-9]+ /, "", n)} n == k {print $3}' "$X/readback.txt")
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
