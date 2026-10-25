#!/usr/bin/env bash
# S1-setup-start.sh, an extra machine (root, through rust-split/ssm-rs.sh, which adds RS_PART and
# RS_NAME; made by render.sh from src/S1-setup-start.body). Idempotent: a second run only checks.
#   1. the same packages as R1 of machine A (git python3.12 xfsprogs tar, and zstd);
#   2. the input of s3://B/dataset-x1k/rust-split/input/ (all but the clone) to /rs/in, sha256 checked;
#   3. the clone: streamed from S3 through sha256 and zstd into /rs/repo (no copy of the tar.zst on
#      disk); the sha256 must be the one in SHA256SUMS; the repo path string of machine A is a
#      symlink to it; HEAD and a clean worktree as on A;
#   4. the cregit tree of the row (cregit.tar.zst) at /rs/cregit-ec2: HEAD 57551d7, clean, the
#      57551d7 blobs of formatBlame.pl and blameRepoFiles.pl, its build dir on the file system of
#      /rs/out (formatBlame.pl renames the temp file into the out dir: then the rename is atomic);
#   5. the tools of the blame environment (blame.env of A's step 7): the same git binary path and
#      version, the same perl version, the Perl modules of formatBlame.pl;
#   6. /etc/rust-split/rs.env (part, jobs = nproc - 8, capped by memory, margin), the units
#      rs-upload (loop) and rs-run (gate, then blame, then the end); starts both.
# Env: JOBS (default nproc - 8), MEM_PER_JOB_GIB (1.5), MARGIN (300), UPLOAD_EVERY (600),
# GATE_FAIL_HOLD (3600). Output: counts only; each at sign is dropped.
set -uo pipefail
# Test hooks (test/t_e1s1.py only): X1K_ASSET, RS_BASE (/rs), RS_ETC (/etc/rust-split), RS_LIB, RS_BIN,
# RS_BUCKET, RS_SUDO ("sudo -u ec2-user", split into words on purpose), SYSTEMCTL, RS_RESERVE_GB (20),
# RS_TEST (no dnf, no chown, no units).
IID=$(cat "${X1K_ASSET:-/sys/devices/virtual/dmi/id/board_asset_tag}")
RS=${RS_BASE:-/rs}; ETC=${RS_ETC:-/etc/rust-split}; BIN=${RS_BIN:-/usr/local/bin}; SU=${RS_SUDO-sudo -u ec2-user}
SYSTEMCTL=${SYSTEMCTL:-systemctl}
own() { [ -n "${RS_TEST:-}" ] || chown "$@"; }
case $IID in ${RUNNER_EC2_BIG}|${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_X1K_A}|${RUNNER_EC2_X1K_LONG_A2}|${RUNNER_EC2_X1K_B1}|${RUNNER_EC2_X1K_B2}|${RUNNER_EC2_X1K_LONG_A4}|${RUNNER_EC2_PATHFIX_B1}|${RUNNER_EC2_V0_ORG_1}|${RUNNER_EC2_X1K_RAW_1}|${RUNNER_EC2_X1K_LONG_A1}|${RUNNER_EC2_X1K_LONG_A3})
  echo "ABORT: $IID is on the refuse list, not an extra machine"; exit 1 ;; esac
K=${RS_PART:-}; NAME=${RS_NAME:-}
case $K in ''|*[!0-9]*) echo "ABORT: RS_PART is not set (run S1 through ssm-rs.sh)"; exit 1 ;; esac
B=${RS_BUCKET:-s3://${RUNNER_BUCKET}}
S3=$B/dataset-x1k/rust-split
FB_SHA=788acb9abac05782058c6b0b599b349caf63b85fa49b8375af9240be7bc0b435
MARGIN=${MARGIN:-300}; UPLOAD_EVERY=${UPLOAD_EVERY:-600}; GATE_FAIL_HOLD=${GATE_FAIL_HOLD:-3600}; MPJ=${MEM_PER_JOB_GIB:-1.5}
LIB=${RS_LIB:-/usr/local/lib/rust-split}

main() {
echo "== $(date -u +%FT%TZ) S1 on $IID part $K ($NAME): $(nproc) vCPU $(free -g | awk '/Mem:/{print $2}') GiB"
if $SYSTEMCTL is-active -q rs-run.service; then echo "rs-run is active already: nothing changed"; return 0; fi
# 1. packages
[ -n "${RS_TEST:-}" ] || for i in $(seq 1 40); do dnf -y -q install git python3.12 xfsprogs tar zstd >/dev/null 2>&1 && break; echo "dnf busy, retry $i"; sleep 15; done
command -v zstd > /dev/null || { echo "ABORT: no zstd"; return 1; }
mkdir -p $RS/in $RS/repo $RS/out/blame $RS/state $RS/logs $RS/batches $RS/gate $RS/control $ETC
own ec2-user: $RS/out $RS/out/blame $RS/logs $RS/state $RS/control
echo setup > $RS/state/phase
# 2. input
aws s3 cp "$S3/input/" $RS/in/ --recursive --exclude clone.tar.zst --only-show-errors || { echo "ABORT: input download"; return 1; }
(cd $RS/in && grep -v '  clone.tar.zst$' SHA256SUMS | sha256sum --quiet -c) || { echo "ABORT: input sha256"; return 1; }
[ -s "$RS/in/parts/part-$K.tsv" ] || { echo "ABORT: no part-$K.tsv in the input"; return 1; }
get() { sed -n "s/^$1=//p" $RS/in/settings.env | head -1; }
local REPO CB WANT_CLONE
REPO=$(get REPO); CB=$(get CLONE_BYTES); WANT_CLONE=$(awk '$2 == "clone.tar.zst" {print $1}' $RS/in/SHA256SUMS)
[ "$(get N)" -ge "$K" ] || { echo "ABORT: part $K is not in the split (N=$(get N))"; return 1; }
echo "input: $(wc -l < $RS/in/SHA256SUMS) files ok; E1 $(get E1_TIME); part $K: $(wc -l < "$RS/in/parts/part-$K.tsv") files"
# 3. clone
local RB
RB=$(basename "$REPO")
if [ ! -e $RS/state/CLONE-OK ]; then
  local free
  free=$(df -B1 --output=avail $RS | tail -1)
  local rsv=${RS_RESERVE_GB:-20}
  [ "$free" -gt $((CB + CB / 5 + rsv * 1000000000)) ] || { echo "ABORT: $RS has $((free / 1000000000)) GB free; the clone needs $((CB / 1000000000)) GB plus 20 percent plus $rsv GB (relaunch with a larger ROOT_GB)"; return 1; }
  rm -rf "$RS/repo/$RB" $RS/repo/.x; mkdir -p $RS/repo/.x
  local F=$RS/state/clone.fifo t0
  rm -f $F; mkfifo $F
  sha256sum < $F | cut -d' ' -f1 > $RS/state/clone.sha256 & local s1=$!
  t0=$(date +%s)
  aws s3 cp "$S3/input/clone.tar.zst" - --only-show-errors | tee $F | zstd -q -dc | tar -C $RS/repo/.x -xf -
  local prc=("${PIPESTATUS[@]}")
  wait $s1; rm -f $F
  if [ "${prc[*]}" != "0 0 0 0" ] || [ "$(cat $RS/state/clone.sha256)" != "$WANT_CLONE" ]; then
    rm -rf $RS/repo/.x; echo "ABORT: clone download rc ${prc[*]} or sha256 differs"; return 1
  fi
  mv "$RS/repo/.x/$RB" "$RS/repo/$RB" && rmdir $RS/repo/.x || { echo "ABORT: clone layout"; return 1; }
  touch $RS/state/CLONE-OK
  echo "clone: $(du -sb "$RS/repo/$RB" | awk '{print int($1 / 1000000)}') MB in $(( $(date +%s) - t0 )) s, sha256 ok"
fi
mkdir -p "$(dirname "$REPO")"
[ -e "$REPO" ] || ln -s "$RS/repo/$RB" "$REPO"
[ "$(readlink -f "$REPO")" = "$RS/repo/$RB" ] || { echo "ABORT: $REPO is not the clone"; return 1; }
own ec2-user: "$RS/repo/$RB"
[ "$(stat -c %U "$RS/repo/$RB/.git/HEAD")" = ec2-user ] || own -R ec2-user: "$RS/repo/$RB"
[ "$($SU git -C "$REPO" rev-parse HEAD)" = "$(get REPO_HEAD)" ] || { echo "ABORT: HEAD differs from A"; return 1; }
[ -z "$($SU git -C "$REPO" status --porcelain --untracked-files=no | head -1)" ] || { echo "ABORT: the worktree is not clean"; return 1; }
echo "repo: HEAD as A, clean worktree, path string of A"
# 4. cregit
local CR=$RS/cregit-ec2 CB2
CB2=$(basename "$(get CREGIT_DIR)")
if [ ! -d $CR ]; then
  rm -rf $RS/cregit.x; mkdir -p $RS/cregit.x
  zstd -q -dc $RS/in/cregit.tar.zst | tar -C $RS/cregit.x -xf - || { echo "ABORT: cregit unpack"; return 1; }
  mv "$RS/cregit.x/$CB2" $CR && rmdir $RS/cregit.x
fi
mkdir -p $CR/blameRepo/build $CR/tokenizeByBlobId/build; own -R ec2-user: $CR
[ "$($SU git -C $CR rev-parse HEAD)" = "$(get CREGIT_COMMIT)" ] || { echo "ABORT: cregit is not at 57551d7"; return 1; }
[ -z "$($SU git -C $CR status --porcelain --untracked-files=no)" ] || { echo "ABORT: cregit is dirty"; return 1; }
[ "$($SU git hash-object $CR/blameRepo/formatBlame.pl)" = "$(get FB_BLOB)" ] || { echo "ABORT: formatBlame.pl blob"; return 1; }
[ "$($SU git hash-object $CR/blameRepo/blameRepoFiles.pl)" = "$(get BRF_BLOB)" ] || { echo "ABORT: blameRepoFiles.pl blob"; return 1; }
[ "$(sha256sum $CR/blameRepo/formatBlame.pl | cut -d' ' -f1)" = $FB_SHA ] || { echo "ABORT: formatBlame.pl sha256"; return 1; }
[ "$(stat -c %d $CR/blameRepo/build)" = "$(stat -c %d $RS/out/blame)" ] || { echo "ABORT: the build dir and the out dir are on different file systems"; return 1; }
echo "cregit: 57551d7, clean, formatBlame.pl and blameRepoFiles.pl are the 57551d7 blobs; build dir and out dir on one file system"
# 5. tools
cp $RS/in/blame.env $ETC/blame.env
local ENVV GE GV
mapfile -t ENVV < $ETC/blame.env
GE=$(get GIT_EXE); GV=$(get GIT_VERSION)
[ -x "$GE" ] || { echo "ABORT: the git of A ($GE) is not on this machine"; return 1; }
[ "$("$GE" --version)" = "$GV" ] || { echo "ABORT: $GE is not $GV"; return 1; }
[ "$($SU env -i "${ENVV[@]}" git --version)" = "$GV" ] || { echo "ABORT: git in the blame PATH is not $GV"; return 1; }
local gr
gr=$(readlink -f "$($SU env -i "${ENVV[@]}" bash -c 'command -v git')")
[ "$gr" = "$(readlink -f "$GE")" ] || echo "WARNING: git in the blame PATH is $gr, A ran $GE (same version)"
[ "$($SU env -i "${ENVV[@]}" perl -e 'print $^V')" = "$(get PERL_VERSION)" ] || { echo "ABORT: perl in the blame PATH is not $(get PERL_VERSION)"; return 1; }
$SU env -i "${ENVV[@]}" perl -MFile::Basename -MFile::Path -MFile::Temp -MFile::Copy -MGetopt::Long -MPod::Usage -MFindBin -MPOSIX -MErrno -e 1 \
  || { echo "ABORT: a Perl module is missing"; return 1; }
$SU git -C "$REPO" config --list --show-scope 2>/dev/null | grep -v -E '^[a-z]+[[:space:]]+(user|credential|sendemail|safe)\.' | sed 's/@//g' > $RS/state/gitconfig.here
if ! diff -q $RS/in/gitconfig.txt $RS/state/gitconfig.here > /dev/null; then
  echo "WARNING: git config differs from A in these keys: $(diff $RS/in/gitconfig.txt $RS/state/gitconfig.here | sed -n 's/^[<>] [a-z]*[[:space:]]*\([^=]*\)=.*/\1/p' | sort -u | tr '\n' ' ')"
fi
echo "tools: $GV at the path of A; perl $(get PERL_VERSION); Perl modules ok; CREGIT_C100_LIMIT $(sed -n 's/^CREGIT_C100_LIMIT=//p' $ETC/blame.env | grep . || echo 'not set (3600 s)')"
# 6. config and units
local J MEMG MJ
MEMG=$(awk '/MemTotal/ {print int($2 / 1048576)}' /proc/meminfo)
J=${JOBS:-$(( $(nproc) - 8 ))}
MJ=$(awk -v m="$MEMG" -v p="$MPJ" 'BEGIN {print int((m - 16) / p)}')
[ "$J" -le "$MJ" ] || { echo "jobs $J capped by memory to $MJ ($MEMG GiB, $MPJ GiB per job)"; J=$MJ; }
[ "$J" -ge 1 ] || { echo "ABORT: jobs $J"; return 1; }
{ echo "K=$K"; echo "NAME=$NAME"; echo "JOBS=$J"; echo "MARGIN=$MARGIN"; echo "UPLOAD_EVERY=$UPLOAD_EVERY"
  echo "GATE_FAIL_HOLD=$GATE_FAIL_HOLD"; echo "S3=$S3"; echo "REPO=$REPO"; echo "CREGIT=$CR"; } > $ETC/rs.env
# Until rs-upload gets control/a-pos.txt from machine A, the A rule uses A's index at E1.
[ -s $RS/control/apos ] || echo "$(get APOS0) 0" > $RS/control/apos
mkdir -p $LIB
# embedded lib/rs_blame.pl (sha256 4b27f8ea48a4eda1)
mkdir -p "$(dirname "$LIB/rs_blame.pl")"
base64 -d <<'EOF_RS_EMBED' | gunzip > "$LIB/rs_blame.pl.tmp"
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
EOF_RS_EMBED
[ "$(sha256sum < "$LIB/rs_blame.pl.tmp" | cut -d" " -f1)" = 4b27f8ea48a4eda11d4072d40bc71bf7f61b067a71ff3ddffdb3cec43a5361bf ] || { echo "ABORT: embedded lib/rs_blame.pl sha256"; exit 1; }
chmod 755 "$LIB/rs_blame.pl.tmp" && mv -f "$LIB/rs_blame.pl.tmp" "$LIB/rs_blame.pl"
# embedded lib/rs_gate.sh (sha256 5bc346586d9ee102)
mkdir -p "$(dirname "$LIB/rs_gate.sh")"
base64 -d <<'EOF_RS_EMBED' | gunzip > "$LIB/rs_gate.sh.tmp"
H4sIAAAAAAAC/21T227TQBB9z1ccXNPEojakQB+S2FJQUxG1olJSJCSKqo29qa046+DdUBfCvzOz
m0spSNbanplz5sxlj6BzWZZpLtOF+4xnQuetI9T67l4YGem8B5NL8A/SarkStUQ1h1CQjakFliLN
CyXR0dW6TmXWBzME0YHjbge7Gk9vMDwfT/CFj8lo+vnqhuJgPT14uvgpBzfDD4kSS+lhJWuXd16U
MrLI3j7fsK0RzUoKtG4dWVIn9qnd8i9FJpHLmlhGhMdKFDUKvSsow+yR01S1++iky1UQbQXiXhqN
ilKWnJdFMXHPEnsDleD6cnM+vrjYfLoOh3x8HE1GGOhcnL4/414NT9A9S/YW1rG1cJ2JF1mqqcmq
tekdMnlcew+DapFAfl+L8gSDmcgSqMo4A5OTAA8dVYG5dOC4JtKsa6XxhtjKRzzkksb1Q9aPVjpX
7vBCZbZhZaENcqEhDEop6IdV2La3nk2xE+BXCyirlPCMi/0uRFbUsX+Kxr7fopY69t9BxSRgQQfJ
ppMVQqAB8WsB3RBPDwk8n+I9bDaEY904JcdDzkrHF9PYb9+aNrlEhrDGnaXpI6soCPiKUBGBW5hv
zJFWyhRqLa1bxX6no/AK3SDoQ8Sez1Jf23i3JV4fDZmb52YL1yIO+yQ0DnfJ5pRMcKbjY/b6HTdU
vV5i4FykYG0Qpt2wexY8hTU7WPMPrPkfrJgT8sUhZZ9Hpah5MS+aDZHl06DmeRAv4iGOlhqhRhg6
Po4/RF9fbgO15F/e5z4twFa/52vjIaZNdyXQUKmv1cI1lrvOEyYTvZzNAld1ocwc7ZcZXur9c6va
PDFvy0qnVaMbbz/IZLcURJPxKnKTeNnYINO82l0OnzRs74bPuf+6GpSj5dRTsvDe0HWw6tlCwVwQ
WVq/W38AmI1q9wcFAAA=
EOF_RS_EMBED
[ "$(sha256sum < "$LIB/rs_gate.sh.tmp" | cut -d" " -f1)" = 5bc346586d9ee102e18bf911de8e4472ea365b9293d4042d388469dd0f78b151 ] || { echo "ABORT: embedded lib/rs_gate.sh sha256"; exit 1; }
chmod 644 "$LIB/rs_gate.sh.tmp" && mv -f "$LIB/rs_gate.sh.tmp" "$LIB/rs_gate.sh"
# embedded lib/rs_batch.sh (sha256 b37bfb42f218bc53)
mkdir -p "$(dirname "$LIB/rs_batch.sh")"
base64 -d <<'EOF_RS_EMBED' | gunzip > "$LIB/rs_batch.sh.tmp"
H4sIAAAAAAAC/4VWTW/jNhC951cMHHdttaZsx9s92Guj3nQPBQI0XXvRQxoE+qAjIZLokFRcb5L/
3kdSUmQnQS+CRL55M/NmONQpqYRnWZTw6M69zsNAJSenJNVNGOgo8VUyJZ1wsl9ckdhQUBD/V8uA
8iBK0oJTX4lSRjyekbH2fNgvnQGlikL2WfH7ha8D6f9QmvqGruA78sMsyDlt0owrb9DgsrQCpZIK
AJQHjzE4a4BKgrNfP1EfoRiqitfzaSNkHugvhtXfZrSTqUbEHFHWvrSggDTPt9YrpYVliCS/TbXx
UKZZTDEcwyNJbt1TqgGEpYGKUtt9m4Sqwye1V2AdkFWSxxTuaTVGTkoQf+ByD+6fqxAqnzURBIpE
vs245n6jmg7ujNRFtgdWKO50MLquYVpuMxHEpHgRK8tVK5IFSk+bqiwrmqAitXS7hBcUZBlNnO6o
JOQ2zCsd6KoYJsbVegoP99Q3pFSUecilSYgXuqpQJU5h4s9TrU3arkmA2yK4tLi1OoHc2dvmqVNM
Am27A5JrPOFDaNpzbV3MrOjKvlNwG8BLyFFeDnvTOgL51cbot1bD3rga/vl9jRToy+9T2kpUzwll
Eqq6popCWBldOeuYQT4gIV9ceQM4wAIiTAzAiggLaYMohMUZ5Xz6xnUpC7NYsB9cCpjb8yKlkP7J
YZB9jx5PiDIRBZnph3l3TArPMwrjeXdChY03BCTd0BUxRZ2u0sMqzA5dz0wQ0B9KHuzM0LomDBrN
EBbstSiRrMU0BezQ01ONGwPTj2IgEEaHPnyAGVTxien9Fk1BzBSbelUP94hZUTfU++nyn6Ln0RNd
nN8sLy7m52h5qWnhnEWlfNPXIZiVr0JbtFYMhsfvUpjuI3Y2Ofb4mqAiRbHeDKqYd/u7iFhGn4+A
HnavsFZ0iN1qGtF1y3SETdQJxk0d8Nmhs8Uw5g/DosRhA5pHiaCR14AbAUef4h51+/3x6LRr6v0L
jT3P4MJ5N4yHITOr+MzvzLhgW7gIX6mBGUjsvK4fY5g5aLQ0Z/Y8s40U0Gh9nD+LUFnUDtMzJnYP
xEdiE2LC+Kjnta/zLaCbplNlNO93uo+Xf1x+Xa2X6++rq9+unxuNHmV0NcI3za1OaKV6dfyyiuAf
SSKkzStPTe+OZ/Rs0n54C9VesP0abY+TM4j3+9xICDM3OFWZU8cJ/UK6aJYcyPmFTRXRG5uHax3v
yLNtgU7Xdsei1SngfGOrOebvkpw8Hww+N4bd1KPV17+mFGw0N2NsY3rQ3RruMnejOxKlma5uyg5a
U9FdAreiNbAc+cHEUnZgmVF15np6gi13Bpq+rY/z4n+GT90L7bzbNE1V2ouVzMdnw3ppV+pVOA1q
eKxhdbWuJpfLb7WOdLX8e3U9bf9rOLEM2cCNYHu5uE44OSI71GxyrBkFOzXvPn6cMrw8mx8rgHHT
mTf7r1D9Ndk717mYUSwAIuQBmw5IXfu/pNmFsZ2Ak2F1JR/uMGZ+BphKxI7Zq0kd1SPGrQdp/gNb
vSohIAoAAA==
EOF_RS_EMBED
[ "$(sha256sum < "$LIB/rs_batch.sh.tmp" | cut -d" " -f1)" = b37bfb42f218bc53e1a3a53e00ff98f5d70b80db93e3645bff4ae5066ad9dc8c ] || { echo "ABORT: embedded lib/rs_batch.sh sha256"; exit 1; }
chmod 644 "$LIB/rs_batch.sh.tmp" && mv -f "$LIB/rs_batch.sh.tmp" "$LIB/rs_batch.sh"
# embedded lib/rs-run.sh (sha256 8202dd76c22bbe14)
mkdir -p "$(dirname "$BIN/rs-run")"
base64 -d <<'EOF_RS_EMBED' | gunzip > "$BIN/rs-run.tmp"
H4sIAAAAAAAC/7VYe1fbyBX/X5/iRihrK4tsDNn01I5pnECyNCxwsLPpaZzlyPYYq8iSVjPmsYTv
3t+dGdkSmCw9bXNyEnnmzn2/N541FzJvjqKkKZJLGoVy5mxQLoN8kVA9TEhcqzykeTieRYnYpDxN
VcfeN6TIL6MxTqUKcyUmNLqhfiuQQi2yQJ815MxvACFRq0FqJug8VILqaTIWfptGcTgXq+NpFAtJ
dUuLejhIIjkDXoDMfbqK1ExDS342DuOYwmSiseMP2I/yNJmLRG3SOJ1nYS7AEONNc/OhEfRqkhqG
siWYyzOmr3mlXnJDk2g6FbkAk22mV1CYh/mFyOlDb7AfvO8dHO7vbVKSGik2KUuvcJlOpxROlQU7
Y7Czn48P9wh0FgnISWrmsnl0fNb/+dNg7/jzkdXPdoNyIRdzQ5IS4JTApn+MQjWeFT8jSRBN4StU
1N+hWSgpjHMRTm5gMCCJw0UynvkU7JK8iDKKI6k6hQxLdJQs5iOweZ4y4sQyzddxmJ8LqXAoKEpA
wjC4YwyopW3DA870VyOLKb3ES83Tx02a5um8giZKJuKaJulVskl/P37bJ7AdkopYZ6FcWm+8HSzg
Tysjl+zJgrPZpBIZ/YXqhjIAYK8DheM0k4x2nCYqT+Nmf3B8QjD61UwkBYFI0VwIJWnlXnXD2usu
hUGWSvqRfumdfjgoLPKyYfmYtK1AkMboDi4TLLI4DScUBOzMCAyh8khMfAhFMNb4whhIQDc3FKfw
1sLrrlZSS+2sjNz61t7x0T7CIycW4WR/z5ol1L99DZqUPK3OT6MEoQYeCJDzKIEny6W5o2kZu2V5
Gkax3CwpQgr4AMNpI8KfloHHGuToVgvZUNcwJhshjIVVEf70EoK7xSLMWVN0lUfKIrNEe4f7pwMO
VMO3/E6IdCAoMwfCrOyChGXbov4Ovh26foCz4SAdUbBIKYsywdiBdsCOOUvTC9mm0/7Z214fWkdc
QsP4uT94h19CjZv5QqpAZnGkzM3hwVv9/6eTw+PeHoA4d2rj6gy69Ap/E0QAV8Q41V05WygOAgoQ
eumVaxCefjrq9XGLbKq9P1isIiEI3A5p4jCxSukqzSc6VLNFDndlG5z2u96tFaAdgP5dh8C9OcQH
zqpi3DmGdQNhvgH0iBjAVkhgHhS/2sE9cQCpRTFg+jNYL9Od0yDXA28gwyHsOlCqeYaPCi9xNKqw
zg8B01zla9eZhxlncQoU7R/9+iu9Jo17mSGc/s5J1+vvNNOFanofnTg9r/t0C45mKblfvPqEKw9Y
/PH5+8HzwT/9r+S9cOkbYmJCNdl802ye1zp052TIs6L01Gu5tEveab/J4SGa+r6DSD8nV38TIPhh
KM9YdP3UM/bmShtEwHHLPH958/XOxY83GtxEjYamjSKGjnq/7NNg/x+DtokC7f42LFiw1xe7TYZx
qOBum7lzV+yBGVxyJTzjpN6ibUTLS/qpg8xM4RXCeofG2b0X+An16S9Oc/ENzJ5eBSLPU8TdDz9w
0lvkCW3BT2OB3LyzxfgSAVJaEQWLlSzktWyQQ16LoOVAwRzNZwjmQvblAX3uHQzO+o5OZ18oEFrt
pRJKXzsmM2qipYs21+dlulzRA5vTCPi+GDsG54q26CtLdGstuEyxUBYYlm4homvNSo9wUkLyNEbu
CmWVr73iIRTjjCeg+u50/8PBAJ75DS0ZUkLLQZJeXRiPPxVZ2hwtongCoebh9URkqKYtCridoJqa
62AJXtQomIhYwJG2d5sTcdlMFjHnxVKT5mhdPytkND6hW5/jj4W+wblxdf2AKJ9TkE+NE/ERBx2E
mV9MIoR+du+i7Gx8CEioNOFjjhLX6BLujCxTJJD2n+EAF+HVBQXva0NVo9rRe9rtwtdvsxw5lI5O
yR2qrSEeett3NS0ZEt558byh5GUlqvkw4KrIN4zbBDNlIo9X2ajohDhMEGLzUOmT7hrjmOu3pQf/
SkcSkPWrMQUx56/1xH2Xhg5Xw0AfdR8BwzXC7DxKugHMHmiIe7Css/2TY5fKmqRdIzY8URpV8OH2
g1N8mTi0Sfis6LTXqrJ8GFbpVXlqcO8bqwe6b6Ajhjw3S3+zseLVx6F6BNZ3Ndwqqa0nZXKbYfVa
rctwGo1KF2j4HoQAZ9pYiidy1C4NOSb1/S9ZXMVgYLA766cVcksc0MPS16YnqHWVlV2v2mshfm1m
Is6u+LuxmmrMXNDfMXXUHjpWAbG0otpBp3mveMmdwN4YPZSTVvs+KPfUDZ55XEcPfjqD1zkp1GwW
8F4i9L+D3hR/ZCLU/9+G9VHwZSv469fh7avh3dAfou0It3965TWHrWZWY+A0Vz7XPch9nqNEBL8T
gmvUwADc+EOqoed+jxpyXOUVs/4nT1ADeNSJkoVwqFK9y0q0uOA266r37qNqY/S2ghUTKZ+Dt1Xd
Nobm4qXLPQaw7n+h41EwrFd13HhRUS/+UyBNQcs3dUmXCVC1RYLreL3e2trgM983Fb040j5dZkX8
XnEhXVK5a9ry+WnRS9hGShPZvf9e9w8btFSamcRMuyPymvQxXcTo1t3XXHl3zeTnasw0yaNLhllN
51Vgt+GYpFOhuXTqw3dnvcPD7jujGITvY2Zc+/y+KDifCwzqE+2Ic9SP6aMA6/mxjfLQyOg1m7Un
UYbsDZaAc2HF11aVcC0a365G+IRGAiGO4buy0fhPDO46T2051rC9UdmJFJltkTjcB01LaRSDsfP/
6xx4qWKaA9sauLbs8g+p/w28j1yP+RFL0F0rEC5DzJUBt4gaolin8KnFz6uWhwB637JsPFzPrFHc
h/1HpfXgwcVsRMpdhomOh92H0RS3H/m46/3NgU6RcsYACyZo9KDwVlXjZYv7xsUMbsrH5OXjTb2v
8G55vxMkyGJ37Hs2zazjx2eLr5ZC1t7owsPYzstOetHdch4OWfTKlgfkLs/uDszeqNTX1NHmV9UC
V9Q9fgPT7U0GUkUf/8LEGoTWyXZKtecnw6TmI01Ws0O5ndKMNvRkrek9yCNrom0NAr5z7GoJsfMH
p9klKjSDcP3tnfVk1+ICzzPBe7RWKfdCjyguo1yEF3ZS0/+YCezVlik63Jd0Xb2y8j4+MKa18iNt
znfMfG/2R2WfCe5v1zToZdnK3maS0+Mv9HXlwclh7+AoeHvIc75XN/3AmGq/lc9ra4IBPqnt4KUX
9KwLj1tNZhs0mBUrbr2K5C49SZXZ6fIa74bSjJWdVHaiSnJ3pvQmUBXOrsuUNHv4TXiMxq930eNU
X+h1LmOHtsMGfQ7RH6xZx3FshJwDZZrc32Y2luOkiSbbzHaqi0S3tMQUE9iS3cC1i5flmrYChNtV
14qm4B5PL2jH9zurqdoZ6+0NSx3pEZcTKH59mwsV9HzLo8s+6HYqi1u3YGZFbos6HfZc7kvsS/7O
SnIVq97HX78onoaxyNUDhazWryt1PKFNZ9xChmPn3yPMbpYEGgAA
EOF_RS_EMBED
[ "$(sha256sum < "$BIN/rs-run.tmp" | cut -d" " -f1)" = 8202dd76c22bbe14087be6061e65bea7a83a7279944bc8d92d474cb011b9f464 ] || { echo "ABORT: embedded lib/rs-run.sh sha256"; exit 1; }
chmod 755 "$BIN/rs-run.tmp" && mv -f "$BIN/rs-run.tmp" "$BIN/rs-run"
# embedded lib/rs-upload.sh (sha256 05acd1bbd03966e4)
mkdir -p "$(dirname "$BIN/rs-upload")"
base64 -d <<'EOF_RS_EMBED' | gunzip > "$BIN/rs-upload.tmp"
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
EOF_RS_EMBED
[ "$(sha256sum < "$BIN/rs-upload.tmp" | cut -d" " -f1)" = 05acd1bbd03966e4067d3458df4b3d48b06d89447ab46c7116e09a3e19d32ca5 ] || { echo "ABORT: embedded lib/rs-upload.sh sha256"; exit 1; }
chmod 755 "$BIN/rs-upload.tmp" && mv -f "$BIN/rs-upload.tmp" "$BIN/rs-upload"
mkdir -p $RS/in/gate/a; own -R ec2-user: $RS/in/gate $RS/gate
if [ -n "${RS_TEST:-}" ]; then echo "RS_TEST: units not written, not started"; return 0; fi
cat > /etc/systemd/system/rs-upload.service <<'EOF_u'
[Unit]
Description=rust-split upload loop (batches of finished .blame files to S3, status, control files)
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
ExecStart=/usr/local/bin/rs-upload
Restart=always
RestartSec=30
EOF_u
cat > /etc/systemd/system/rs-run.service <<'EOF_r'
[Unit]
Description=rust-split blame of one part (gate, blame, end)
Wants=network-online.target rs-upload.service
After=network-online.target nix-daemon.service rs-upload.service
[Service]
Type=simple
ExecStart=/usr/local/bin/rs-run
StandardOutput=append:/rs/logs/run.log
StandardError=append:/rs/logs/run.log
Restart=no
KillMode=control-group
TimeoutStopSec=60
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
EOF_r
systemctl daemon-reload
systemctl enable --now rs-upload.service >/dev/null 2>&1
sleep 5
"$BIN/rs-upload" --once || echo "WARNING: the first status upload failed"
systemctl start rs-run.service
sleep 30
echo "units: rs-upload $(systemctl is-active rs-upload), rs-run $(systemctl is-active rs-run); phase $(cat $RS/state/phase); jobs $J, margin $MARGIN"
echo "S1 done $(date -u +%FT%TZ)"
}

main 2>&1 | sed -u 's/@//g'
exit "${PIPESTATUS[0]}"
