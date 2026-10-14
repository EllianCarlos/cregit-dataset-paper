#!/usr/bin/env bash
# stage-cregit.sh COMMIT [REPO] (local): stage the git bundle of a new cregit commit for the fed parts and
# batch6L. The bundle holds the branch that contains COMMIT, from 95cdc88 (the AMI cregit, which every
# copy on the instances has) to COMMIT; it is verified against a repo that has 95cdc88. Writes
# upload-cregit/cregit-<short>.bundle and upload-cregit/SHA256SUMS and prints the upload command for
# the user (Claude's aws s3 cp is denied) and the bundle sha256 for census-fed-workload / feed.tsv.
set -euo pipefail
C=${1:?commit}; R=${2:-${RUNNER_PROJECTS}/cregit-trailers}
cd "$(dirname "$0")"; U=upload-cregit; mkdir -p $U
full=$(git -C "$R" rev-parse --verify "$C^{commit}"); short=${full:0:7}
git -C "$R" merge-base --is-ancestor 95cdc881e5c8f736c87487139849388575f20d91 $full || { echo "$short does not contain 95cdc88" >&2; exit 1; }
[ -z "$(git -C "$R" status --porcelain --untracked-files=no)" ] || echo "note: $R has uncommitted changes (not in the bundle)"
# a scratch clone, so the source repo (another session's worktree) gets no new ref
W=$(mktemp -d /tmp/stage-cregit.XXXX); git clone -q --no-checkout "$R" $W/r
git -C $W/r branch -f fed-cregit-$short $full
git -C $W/r bundle create "$PWD/$U/cregit-$short.bundle" refs/heads/fed-cregit-$short ^95cdc881e5c8f736c87487139849388575f20d91
git -C $W/r bundle verify "$PWD/$U/cregit-$short.bundle"
git -C $W/r bundle list-heads "$PWD/$U/cregit-$short.bundle"
(cd $U && sha256sum cregit-$short.bundle > SHA256SUMS.$short && cat SHA256SUMS.$short)
echo
echo "upload (user): export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=\"\""
echo "  aws s3 cp $PWD/$U/cregit-$short.bundle s3://${RUNNER_BUCKET}/cregit/cregit-$short.bundle --only-show-errors"
echo "  aws s3 cp $PWD/$U/SHA256SUMS.$short s3://${RUNNER_BUCKET}/cregit/SHA256SUMS.$short --only-show-errors"
echo "commit $full  bundle s3://${RUNNER_BUCKET}/cregit/cregit-$short.bundle  sha256 $(cut -d' ' -f1 $U/SHA256SUMS.$short)"
