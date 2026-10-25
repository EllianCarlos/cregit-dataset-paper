#!/usr/bin/env bash
# S1-stage-cregit.sh [COMMIT] (this machine, main session, AFTER the commit of fix/path-quoting;
# no S3 access): makes the thin cregit bundle of the path-quoting fix for the rerun machines.
#   - COMMIT (default: the tip of fix/path-quoting in ${RUNNER_PROJECTS_TILDE}/cregit-pathfix) must have
#     57551d7 as its only parent and must hold exactly the 3 proven files (blob ids below; the
#     gate and the proof runs of 2026-10-20 used these bytes);
#   - the bundle has one ref, refs/heads/fed-cregit-<sha7>, and needs 95cdc88 (as
#     cregit-57551d7.bundle: every machine copy /data/cregit-ec2 has 95cdc88);
#   - check: a new clone at 95cdc88 fetches the bundle, checks out the commit and must have the
#     same tree as COMMIT;
#   - writes stage/cregit-<sha7>.bundle and stage/SHA256SUMS.<sha7>, and prints the two sha256
#     values for R1/R2 of the rerun (BUNDLE_SHA, CREGIT_COMMIT).
# It never deletes: a new temp folder each run (mktemp), left in place for inspection.
set -euo pipefail
H=${H:-$HOME/s3-work/dataset-pathfix}
SRC=${SRC:-${RUNNER_PROJECTS}/cregit-pathfix}
BASE=57551d7ad82a784615c1490623d72cb9dc994ba1
NEEDS=95cdc881e5c8f736c87487139849388575f20d91
C=${1:-$(git -C "$SRC" rev-parse refs/heads/fix/path-quoting)}
C=$(git -C "$SRC" rev-parse --verify "$C^{commit}")
S7=${C:0:7}
[ "$(git -C "$SRC" rev-list --parents -n 1 "$C" | cut -d" " -f2-)" = "$BASE" ] || { echo "ABORT: $C does not have 57551d7 as its only parent"; exit 1; }
want() { case $1 in
  blameRepo/blameRepoFiles.pl) echo 544cf63d3ce0f4c11975b581792c48b974645a80 ;;
  blameRepo/formatBlame.pl) echo 5f657264dbdaa17e21ff610850fc60dea9548c0e ;;
  tests/t/blamePaths.t) echo fee49aa7536997038a0d19aa2694ea35b50a0292 ;;
  *) echo none ;; esac; }
changed=$(git -C "$SRC" diff --name-only "$BASE" "$C" | sort)
[ "$changed" = "$(printf '%s\n' blameRepo/blameRepoFiles.pl blameRepo/formatBlame.pl tests/t/blamePaths.t)" ] \
  || { echo "ABORT: $C changes other files than the 3 proven ones:"; echo "$changed"; exit 1; }
for f in $changed; do
  [ "$(git -C "$SRC" rev-parse "$C:$f")" = "$(want "$f")" ] || { echo "ABORT: $f in $C is not the proven blob $(want "$f")"; exit 1; }
done
for f in blameRepo/blameRepoFiles.pl blameRepo/formatBlame.pl; do
  [ "$(git -C "$SRC" ls-tree "$C" -- "$f" | cut -c1-6)" = 100755 ] || { echo "ABORT: $f is not 100755 in $C"; exit 1; }
done
T=$(mktemp -d /tmp/pathfix-bundle.XXXXXX)
git clone -q --bare "$SRC" "$T/src.git"
git -C "$T/src.git" update-ref "refs/heads/fed-cregit-$S7" "$C"
git -C "$T/src.git" update-ref refs/heads/base-95cdc88 "$NEEDS"
mkdir -p "$H/stage"
BF=$H/stage/cregit-$S7.bundle
[ -e "$BF" ] && { echo "ABORT: $BF exists; move it aside first"; exit 1; }
TB=$T/cregit-$S7.bundle
git -C "$T/src.git" bundle create "$TB" "refs/heads/fed-cregit-$S7" "^$NEEDS"
# Verify in a new repository that has only 95cdc88 (as the machines).
git clone -q --no-local --single-branch -b base-95cdc88 "$T/src.git" "$T/check"
if git -C "$T/check" cat-file -e "$C^{commit}" 2>/dev/null; then echo "ABORT: the check clone has $C already"; exit 1; fi
git -C "$T/check" bundle verify -q "$TB"
git -C "$T/check" fetch -q "$TB" "+refs/heads/*:refs/remotes/fed-bundle/*"
git -C "$T/check" checkout -q --detach "$C"
[ "$(git -C "$T/check" rev-parse 'HEAD^{tree}')" = "$(git -C "$SRC" rev-parse "$C^{tree}")" ] || { echo "ABORT: tree differs after fetch"; exit 1; }
cp -p "$TB" "$BF"
(cd "$H/stage" && sha256sum "cregit-$S7.bundle" > "SHA256SUMS.$S7")
echo "staged: $BF"
echo "CREGIT_COMMIT=$C"
echo "BUNDLE_SHA=$(cut -d' ' -f1 "$H/stage/SHA256SUMS.$S7")"
echo "bundle size: $(stat -c %s "$BF") bytes; temp folder $T"
