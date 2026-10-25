#!/usr/bin/env bash
# S1-setup-start.sh, an extra machine (root, through java-split/ssm-jv.sh, which adds JV_PART and
# JV_NAME; made by render.sh from src/S1-setup-start.body). Idempotent: a second run only checks.
#   1. the same packages as R1 of machine A (git python3.12 xfsprogs tar, and zstd);
#   2. the input of s3://B/dataset-x1k/java-split/input/ (all but the clone) to /jv/in, sha256 checked;
#   3. the clone: streamed from S3 through sha256 and zstd into /jv/repo (no copy of the tar.zst on
#      disk); the sha256 must be the one in SHA256SUMS; the repo path string of machine A is a
#      symlink to it; HEAD and a clean worktree as on A;
#   4. the cregit tree of the row (cregit.tar.zst) at /jv/cregit-ec2: HEAD 57551d7, clean, the
#      57551d7 blobs of formatBlame.pl and blameRepoFiles.pl, its build dir on the file system of
#      /jv/out (formatBlame.pl renames the temp file into the out dir: then the rename is atomic);
#   5. the tools of the blame environment (blame.env of A's step 7): the same git binary path and
#      version, the same perl version, the Perl modules of formatBlame.pl;
#   6. /etc/java-split/jv.env (part, jobs = nproc - 8, capped by memory, margin), the units
#      jv-upload (loop) and jv-run (gate, then blame, then the end); starts both.
# Env: JOBS (default nproc - 8), MEM_PER_JOB_GIB (1.5), MARGIN (600: A starts about 1,265 files/h, and a-pos is up to 20 min old), UPLOAD_EVERY (600),
# GATE_FAIL_HOLD (3600). Output: counts only; each at sign is dropped.
set -uo pipefail
# Test hooks (test/t_e1s1.py only): X1K_ASSET, JV_BASE (/jv), JV_ETC (/etc/java-split), JV_LIB, JV_BIN,
# JV_BUCKET, JV_SUDO ("sudo -u ec2-user", split into words on purpose), SYSTEMCTL, JV_RESERVE_GB (20),
# JV_TEST (no dnf, no chown, no units).
IID=$(cat "${X1K_ASSET:-/sys/devices/virtual/dmi/id/board_asset_tag}")
RS=${JV_BASE:-/jv}; ETC=${JV_ETC:-/etc/java-split}; BIN=${JV_BIN:-/usr/local/bin}; SU=${JV_SUDO-sudo -u ec2-user}
SYSTEMCTL=${SYSTEMCTL:-systemctl}
own() { [ -n "${JV_TEST:-}" ] || chown "$@"; }
case $IID in ${RUNNER_EC2_BIG}|${RUNNER_EC2_SPOT_A6}|${RUNNER_EC2_X1K_A}|${RUNNER_EC2_X1K_LONG_A2}|${RUNNER_EC2_X1K_B1}|${RUNNER_EC2_X1K_B2}|${RUNNER_EC2_X1K_LONG_A4}|${RUNNER_EC2_PATHFIX_B1}|${RUNNER_EC2_V0_ORG_1}|${RUNNER_EC2_X1K_RAW_1}|${RUNNER_EC2_X1K_LONG_A1}|${RUNNER_EC2_X1K_LONG_A3}|${RUNNER_EC2_RUST_SPLIT_1}|${RUNNER_EC2_RUST_SPLIT_2}|${RUNNER_EC2_RUST_SPLIT_3}|${RUNNER_EC2_RUST_SPLIT_4}|${RUNNER_EC2_RUST_SPLIT_5}|${RUNNER_EC2_RUST_SPLIT_1_R1}|${RUNNER_EC2_RUST_SPLIT_2_R1}|${RUNNER_EC2_RUST_SPLIT_3_R1}|${RUNNER_EC2_RUST_SPLIT_5_R1}|${RUNNER_EC2_RUST_SPLIT_2_R2}|${RUNNER_EC2_RUST_SPLIT_4_R1}|${RUNNER_EC2_RUST_SPLIT_5_R2})
  echo "ABORT: $IID is on the refuse list, not an extra machine"; exit 1 ;; esac
K=${JV_PART:-}; NAME=${JV_NAME:-}
case $K in ''|*[!0-9]*) echo "ABORT: JV_PART is not set (run S1 through ssm-jv.sh)"; exit 1 ;; esac
B=${JV_BUCKET:-s3://${RUNNER_BUCKET}}
S3=$B/dataset-x1k/java-split
FB_SHA=788acb9abac05782058c6b0b599b349caf63b85fa49b8375af9240be7bc0b435
MARGIN=${MARGIN:-600}; UPLOAD_EVERY=${UPLOAD_EVERY:-600}; GATE_FAIL_HOLD=${GATE_FAIL_HOLD:-3600}; MPJ=${MEM_PER_JOB_GIB:-1.5}
LIB=${JV_LIB:-/usr/local/lib/java-split}

main() {
echo "== $(date -u +%FT%TZ) S1 on $IID part $K ($NAME): $(nproc) vCPU $(free -g | awk '/Mem:/{print $2}') GiB"
if $SYSTEMCTL is-active -q jv-run.service; then echo "jv-run is active already: nothing changed"; return 0; fi
# 1. packages
[ -n "${JV_TEST:-}" ] || for i in $(seq 1 40); do dnf -y -q install git python3.12 xfsprogs tar zstd >/dev/null 2>&1 && break; echo "dnf busy, retry $i"; sleep 15; done
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
  local rsv=${JV_RESERVE_GB:-20}
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
  echo "GATE_FAIL_HOLD=$GATE_FAIL_HOLD"; echo "S3=$S3"; echo "REPO=$REPO"; echo "CREGIT=$CR"; } > $ETC/jv.env
# Until jv-upload gets control/a-pos.txt from machine A, the A rule uses A's index at E1.
[ -s $RS/control/apos ] || echo "$(get APOS0) 0" > $RS/control/apos
mkdir -p $LIB
# embedded lib/jv_blame.pl (sha256 4fd05ff9f952a001)
mkdir -p "$(dirname "$LIB/jv_blame.pl")"
base64 -d <<'EOF_JV_EMBED' | gunzip > "$LIB/jv_blame.pl.tmp"
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
EOF_JV_EMBED
[ "$(sha256sum < "$LIB/jv_blame.pl.tmp" | cut -d" " -f1)" = 4fd05ff9f952a001b0a4db8cec4669976791979ab9110696d70198b33b0e6fcf ] || { echo "ABORT: embedded lib/jv_blame.pl sha256"; exit 1; }
chmod 755 "$LIB/jv_blame.pl.tmp" && mv -f "$LIB/jv_blame.pl.tmp" "$LIB/jv_blame.pl"
# embedded lib/jv_gate.sh (sha256 f2d0711cc5c7c869)
mkdir -p "$(dirname "$LIB/jv_gate.sh")"
base64 -d <<'EOF_JV_EMBED' | gunzip > "$LIB/jv_gate.sh.tmp"
H4sIAAAAAAAC/21T227TQBB9z1ccXLeJRR1IgT4ksaWgpiJqRaWkSEgUVRt7U5s469S7aV0I/87M
bi6lIFlre2bOmTOXPYDOZFEkmUzm7jOaCp01DvDj4fZOGNnWWRcmk+AfJOViKSqJcgahIGtTCSxE
kuVKoqXLVZXItAdmCNp7jtst7HI0ucbgbDTGVz7Gw8mXy2uKg/V04en8p+xfDz7GSiykh6WsXN5Z
Xsi2RXZ3+QZNjfa0oEDr1m1L6sQ+t1v+hUglMlkRy5DwWIq8Qq63BaWYPnGasnIfrWSxDNobgbiT
RqOklAXnZVFM3LXEXl/FuLpYn43Oz9efr8IBH5+G4yH6OhMnH065V4NjdE7jnYV1bCxcZ+y1LdXE
pOXKdPeZPK69i345jyHvV6I4Rn8q0hiqNM7A5CTAQ0uVYC4dOK6xNKtKabwltuIJj5mkcT3I6slK
58odXqjUNqzItUEmNIRBIQX9sArb9saLKbYC/GoARZkQnnGR34FI8yryT1Db9ztUUkf+e6iIBMzp
INl0skII1CB+LaBr4ukihudTvIf1mnCsGyfkeMxY6eh8EvnNG9Mkl0gRVri1ND2kJQUB3xAqInAL
8505klKZXK2kdavIb7UUXqMTBD2IyPNZ6hsb77bE66Emc/3SbOFaRGGPhEbhNtmMkgnOdHTEXr/l
hqpXC/SdixSsDMKkE3ZOg+ewegur/4HV/4PlM0K+2qfs8agUNS/iRbMhsngeVL8M4kXcx9FSI9QI
Q8fH8fvoq4tNoJb8y/vcowXY6Pd8bTxEtOmuBBoq9bWcu8Zy13nCZKKXs1ngssqVmaF5mOJQ754b
1eSJeRtWOq0aXXu7QcbbpSCalFeRm8TLxgaZZOX2cvikYXM3fM7919WgHA2nnpKFd4aug1XPFgrm
gsjS+N34A9/CXQ4HBQAA
EOF_JV_EMBED
[ "$(sha256sum < "$LIB/jv_gate.sh.tmp" | cut -d" " -f1)" = f2d0711cc5c7c86964a961196d00ba9e9b781d3b25d4f5dc988a0057c5d3e784 ] || { echo "ABORT: embedded lib/jv_gate.sh sha256"; exit 1; }
chmod 644 "$LIB/jv_gate.sh.tmp" && mv -f "$LIB/jv_gate.sh.tmp" "$LIB/jv_gate.sh"
# embedded lib/jv_batch.sh (sha256 6ce656c7f95c61f6)
mkdir -p "$(dirname "$LIB/jv_batch.sh")"
base64 -d <<'EOF_JV_EMBED' | gunzip > "$LIB/jv_batch.sh.tmp"
H4sIAAAAAAAC/4VWTXPbNhC9+1fsyGwstgIlWWkOUqSp4uTQGc/EjZTpwfV4+AGZrClCBkCriu3/
ngeApCnZnl44JPD27e7bxYLHpFKe53HK41v3Oo1ClR4d07/311Go4zRQ6Zh0ysl+cUViRWFB/D8t
Q1qHcZoVnLpKlDLmyYSMtR/Afu4MKFMUsY+K380CHcrgh9LUNXQF31IQ5eGa0yrLufJ7DS7PKlAm
qQBA+fCYgLMGqDQ8/f0DdRGKoap4/YBWQq5D/cmwBpuctjLTiJgjytqXFhSS5uuN9UpZYRliyW8y
bTyUWZ5QAsfwSJJb95RpAGFpoKLUdt8moerwSe0UWHtkleQJRTtaDJGTEsTvudyB+9cqhMpnTQSB
YrHe5FzzoFFNh7dG6iLfASsUdzoYXZcwLTe5CBNSvEiU5aoVyUOlx01V5hVNWJFaum3KCwrznEZO
d1QSchvmhQ51VQwT42I5hoc76hpSKsp1xKVJiBe6qlAlTmHiX2dam7RdkwC3QXBZcWN1Armzt81T
p5iG2nYHJNd4wofQtOPauphY0ZV9p/AmhJeIo7wc9qZ1BPKrjdFvrYa9djX8+n2JFOjT5zFtJKrn
hDIJVV1TRSGsjK6cdcwg75GQz678HhxgARGmBmBFhIW0QRTC4oxyAX3jupSFWSzYDy4FzO15kVLI
4Gg/yK5PD0dEuYjD3PTD1BuSwvOUomTqjaiw8UaAZCu6JKao4yndr8Ls0NXEBAH9oeTezgSta8Kg
wQRhwV6LEslaTFPADj0+1rghMN04AQJhdOjdO5hBlYCY3m3QFMRMsemk6uETYlbUFZ38cvFPceLT
I52fXc/Pz6dnaHmpaeacxaV81dc+mJUvQpu1VgyGJ29SmO4jdjo69PiSoCJFsV4Nqph63W1MLKeP
B0Afu5dYKzrEbjQN6KplOsAm6gTjpg747NDprJ/w+35R4rABzeNU0MBvwI2Agw/JCXnd7nBw7Jl6
/0ZD3ze4aOpFST9iZhWf61szLtgGLqIXamAGEjur68cYZg4aLVsze57ZSgpotDzMn8WoLGqH6ZkQ
uwPiPbERMWF81PM60OsNoKumU2U87Xa8h4s/L74slvPl98XlH1dPjUYPMr4c4JumVie0Ur06fF5F
8A8kEdLqhaemd4cTejJp37+Gai/Yfo03h8kZxNt9biSEmRucqlxTxwn9TDprlhzI+YVNFdErm/tr
Hf/As22Bjme7Y9bqFHC+stUc8zdJjp72Bp8bw27q0eLLX2MKV5qbMbYyPehuDXeZu9Edi9JMVzdl
e62p6C6BG9EaWI58b2IpO7DMqDp1PT3CljsDTd/Wx3n2P8On7oV23m2apirtxUrmw7NhvbQr9SKc
BtU/1LC6Wheji/m3Wke6nP+9uBq3/zWcWIas50awvVxcJxwdkO1rNjrUjMKtmnoP78cML0/mxwpg
3HTmzf4rVH9N9s51LiaUCIAIecCmA1LX/s9pejC2E3DUr67k/R3GzM8AU6nYMns1qYN6JLj1IM1P
P7h6LSAKAAA=
EOF_JV_EMBED
[ "$(sha256sum < "$LIB/jv_batch.sh.tmp" | cut -d" " -f1)" = 6ce656c7f95c61f653b6387308f83cf5bd136a4f59fe535972c6e4fc6d9e12cf ] || { echo "ABORT: embedded lib/jv_batch.sh sha256"; exit 1; }
chmod 644 "$LIB/jv_batch.sh.tmp" && mv -f "$LIB/jv_batch.sh.tmp" "$LIB/jv_batch.sh"
# embedded lib/jv-run.sh (sha256 e97cc4f55474e52c)
mkdir -p "$(dirname "$BIN/jv-run")"
base64 -d <<'EOF_JV_EMBED' | gunzip > "$BIN/jv-run.tmp"
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
EOF_JV_EMBED
[ "$(sha256sum < "$BIN/jv-run.tmp" | cut -d" " -f1)" = e97cc4f55474e52cb64ca2c81cdea26f7166e77cd50099bf2eb9816774acc8a0 ] || { echo "ABORT: embedded lib/jv-run.sh sha256"; exit 1; }
chmod 755 "$BIN/jv-run.tmp" && mv -f "$BIN/jv-run.tmp" "$BIN/jv-run"
# embedded lib/jv-upload.sh (sha256 375fbf2d4252f867)
mkdir -p "$(dirname "$BIN/jv-upload")"
base64 -d <<'EOF_JV_EMBED' | gunzip > "$BIN/jv-upload.tmp"
H4sIAAAAAAAC/71YbXfaRhb+zq+4q5KAUg8CO3G3UNzarbdN4yQ+ttPTXR8vR0gDyAhJ1QyQrOP/
vs+dEUi8pOluz+kXJM3cl+feuW/DF3/z5ir3hlHiyWRBQ19Nal/Q/ULMszj1Q2r6Ccn3Ovdp5geT
KJEHlKep7pUkLSXzRRRgw6c4TbMeOSW7EGkSSIdGaU5pIsE7T0K3BRXnEEfvLi/env4wOP/l/Oqf
pFhZSL4m5sEPBKos1RQlWub5PNMR1pJUQ5nbJT2RlMglBeksi6WW1BrG/kzSKIqlggJfGY1DX0NR
834xMG8tNQGrn7f+o/QBxRH/QlJCauIfvjh2Saekjrqed+aFvvaV1OJ9Z+rd+wtfqCyOtJfOtffN
9MQz4qTyDqDLStC+nquWfq+pGcBOrQ6AlhKAUu4BZbEfJQZiK07H1GT8lxenL9+Is4vT1+fAkkhA
HkFYpCjzc+0S/AHpMD7NVckFZ858fWasNXuW121Zpx63SXXhlkTnaez5IkstKHFC9atrb72BdXYT
XL5aur55e7lNZtasWjjWeN36OcyjhcwJPgimioYSqACHAcARAM+H/HZ15HyqPukIfM1RnAZTo4M9
Jr0ijHgVTPA4iXlKWZTJkR/FkHIjlaZJmk5h1s+/DM5Or8+p6d0v4FR8nt98jy+pg8oh2Z2Ll2fm
+fL1D9fWhJnUPh8rvbu64FiXUHh13a8/FGK7AmIfewSZdhEvWNsUjn2WaAn4rSsmWmeImc7x163D
F89bxfOx1iKnDhEQ2kJ2OTUgsmx4gVzOPJjtx14cDasaDCNovErYOrXro8t+/frIRGD9VQ3x0HTp
gWQwScm5rTdhmYTv6Msn/7h5cvMv947qzxz6SEqG1FDed543btCJPV4wq9Lz4x491mo2gAca+c6C
a0QGHFJiSpH+kEms4L1fbwbzPCahSMzokMSvdPnuhursCi8GBqURXJEHUmSF+Ikavwp/qYQMDsXq
AITZFFrHQkmEWoijPW43XGgwmnZ0/ETOp6R0qY6nswmASQTTeFECu1BQBMtlBdZfnGBUf2XSk+pv
OANXlATliFdPfVBeKLm2KW8R5XqOgwpnkReF3jD183DgK0TrQPtjlA0Ip7rBTvfpUFH957dn1yia
+ThKqP769OrHl2+ctXaTCbsnRjJLkUDFxpdPlEvZBGFaICpzxq4enjA+L5nHMX38aEUD0TxznQ07
B6YmQsgyIBHTNwguSELJ501lfkX9VUurhVPlzNNxLpXaVb7a2Kc/QdGtCDG1YjCROdswilAJWA5H
sK0i5lRoRMKcQ+OZLeKNTdFkcLuwLQGOpkpzrhEVRLzR4mK+n8/2gG0zlPxtrwXtCvwQ1gxiX+lB
Z/K/GSBmMxy8QDHeC6kUfPT/Ce78fb/kyvlxwxlYYfUmTiwjEVDj39Wm0yiLQdmaKmLdovlsCDjn
pc9ylkDGkbYwBogcJJMysZitBIoRNUBC4ntqPbPNpeGSGR+4CmAjbACoGHXEEXHwBR5v+guk3UzO
BnPUt8E4GrIbcwnHjeEMfzmlhvdazrreQ5ZHHDdHjxCL/voZskMmCyM1HTBZITjEOZz9yOPMXGdz
3UepjmKTRlxgNX+IDr/lQBtQW3xdtZ+TeTv6eLGl5jNUiA+/l0ioy6aDblRkDt086LcpYSXvZUBf
nZzs7ag9su32KxAuJ9zBuz0EH76IpaDOrlrMYDiP4u0gXMs0b8XI4zLGB+IDd2xqWVZu1zJ0egyt
06NhLv0pNxbWdYs4hr+g0qE75je7ZivpbxWm1WQ1FExv8tpxDWk0ojXcYsJ00BEvnSq8Qk3PTGWG
jUouTIuzSO+3a4WvtK6gRtBYLL9rIlkeU6QsOTpTYudRx1DIGEXbEBXgtwVTc8WwHnAxuNkJCnJD
he5I/hh5vQ1hFEEDFxU8Kn2cTqoFrxxQKwEHBvRVDL0UZPuJjYsrC44Z6+MPQk3SpSgKBJzGgCDN
5PUfKDNVaFvD8efhbTFYiJuLfwSmkGU9M+/vEn8Yy71410t28m0hSzYSt2pPObJ/An9lprfYy4XP
4Lb5jPbHKZ2j2+eYL/KAC0UxsxelAslSamYl3s6dwNm5EbT0LNunv2JoJbFmC67ee2VsL/ZwU5il
IR0/f757DSEbvyXiWG0i5luIAw+X3j48edqpILnl49u5t9zZXNbpnPv/1m5vleMVBiV5nuRbG26W
NnNtegMfHGwvn9vD8V8yFt/CIVsK0oo7xJIaTx74HoISF8rHxp8ZmfnWXc7NfsAXb9ehPh2223TH
jsBJMaCHTlc88oa959OdPZHVhbJnS1cPLYpr7remTPHQ02/D+XgG/GKdGvbbtc0GlaTLfmUStvFx
i5Jq6aEVYOjp00JAJRhWEjlA1kdflDWYJlYMtl5/4i+GbvmHBUNx1sYYAzaBraIX6JpNEJOw5rku
xgzJN/Idz1jzYcyy9yn2gtupV/8mcdaiLDQEuDHDfi0jPSlGNmcXaaFJxRKlr/OiZvrFfwFeL/R1
AhIAAA==
EOF_JV_EMBED
[ "$(sha256sum < "$BIN/jv-upload.tmp" | cut -d" " -f1)" = 375fbf2d4252f8673a78d6bb4f140c1c2e431770a4f90bc5b3a5b1ece40680a9 ] || { echo "ABORT: embedded lib/jv-upload.sh sha256"; exit 1; }
chmod 755 "$BIN/jv-upload.tmp" && mv -f "$BIN/jv-upload.tmp" "$BIN/jv-upload"
mkdir -p $RS/in/gate/a; own -R ec2-user: $RS/in/gate $RS/gate
if [ -n "${JV_TEST:-}" ]; then echo "JV_TEST: units not written, not started"; return 0; fi
cat > /etc/systemd/system/jv-upload.service <<'EOF_u'
[Unit]
Description=java-split upload loop (batches of finished .blame files to S3, status, control files)
Wants=network-online.target
After=network-online.target
[Service]
Type=simple
ExecStart=/usr/local/bin/jv-upload
Restart=always
RestartSec=30
EOF_u
cat > /etc/systemd/system/jv-run.service <<'EOF_r'
[Unit]
Description=java-split blame of one part (gate, blame, end)
Wants=network-online.target jv-upload.service
After=network-online.target nix-daemon.service jv-upload.service
[Service]
Type=simple
ExecStart=/usr/local/bin/jv-run
StandardOutput=append:/jv/logs/run.log
StandardError=append:/jv/logs/run.log
Restart=no
KillMode=control-group
TimeoutStopSec=60
OOMPolicy=continue
LimitNOFILE=1048576
LimitNPROC=infinity
EOF_r
systemctl daemon-reload
systemctl enable --now jv-upload.service >/dev/null 2>&1
sleep 5
"$BIN/jv-upload" --once || echo "WARNING: the first status upload failed"
systemctl start jv-run.service
sleep 30
echo "units: jv-upload $(systemctl is-active jv-upload), jv-run $(systemctl is-active jv-run); phase $(cat $RS/state/phase); jobs $J, margin $MARGIN"
echo "S1 done $(date -u +%FT%TZ)"
}

main 2>&1 | sed -u 's/@//g'
exit "${PIPESTATUS[0]}"
