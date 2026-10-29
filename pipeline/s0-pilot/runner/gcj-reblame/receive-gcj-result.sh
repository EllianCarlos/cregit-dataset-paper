#!/usr/bin/env bash
# Receiving side of the gcj re-blame transfer. Run AFTER `fetch-gcj-result.sh serve`
# has the tunnel up on 127.0.0.1:$PORT. Everything here is agent-runnable
# (loopback curl is permitted); no SSM, no S3, no IAM.
#
# Extracts to a STAGING dir, never over the existing pre-C100 blame/ tree.
# Swapping it in is a separate, deliberate step.

set -euo pipefail

PORT=${PORT:-8371}
BASE="http://127.0.0.1:$PORT"
# RUNNER_HOME_LOCAL is the home directory of this machine (see ../../README.md).
DEST=${DEST:-${RUNNER_HOME_LOCAL:?set RUNNER_HOME_LOCAL or DEST}/Projects/cregit-workspace/corpus-files/googleapis__google-cloud-java}
STAGE="$DEST/blame-c100-incoming"
PARTS="$STAGE/.parts"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

say "probing tunnel at $BASE"
curl -sf -o /dev/null -w 'HTTP %{http_code}\n' "$BASE/SHA256SUMS" || {
  echo "tunnel not answering -- is './fetch-gcj-result.sh serve' still running?"; exit 1; }

mkdir -p "$PARTS"
cd "$PARTS"

say "fetching manifest"
curl -sf -o SHA256SUMS "$BASE/SHA256SUMS"
cat SHA256SUMS

# part names come from the manifest, not from guessing the count
mapfile -t NAMES < <(awk '$2 ~ /^gcj-blame\.tar\.gz\.part/ {print $2}' SHA256SUMS)
echo "parts to fetch: ${#NAMES[@]}"
[ "${#NAMES[@]}" -gt 0 ] || { echo "manifest lists no parts"; exit 1; }

say "downloading (resumable)"
for n in "${NAMES[@]}"; do
  printf '%s ' "$n"
  # -C - resumes a partial file; loopback so no retry backoff needed
  curl -sf -C - -o "$n" "$BASE/$n" && echo "ok ($(du -h "$n" | cut -f1))"
done

say "verifying per-part checksums"
grep -v WHOLE-STREAM SHA256SUMS > .parts.sha
sha256sum -c .parts.sha

say "verifying whole-stream checksum"
WANT=$(awk '/WHOLE-STREAM/ {print $1}' SHA256SUMS)
GOT=$(cat $(printf '%s\n' "${NAMES[@]}" | sort) | sha256sum | cut -d' ' -f1)
echo "expected $WANT"
echo "actual   $GOT"
[ "$WANT" = "$GOT" ] || { echo "!! STREAM MISMATCH -- do not extract"; exit 1; }
echo "match"

say "extracting to $STAGE"
cat $(printf '%s\n' "${NAMES[@]}" | sort) | tar -xzf - -C "$STAGE"
echo "extracted"

say "result"
TREE=$(find "$STAGE" -maxdepth 2 -type d -name '*blame*' | head -1)
[ -z "$TREE" ] && TREE="$STAGE"
echo "tree=$TREE"
echo "blame_files=$(find "$TREE" -name '*.blame' | wc -l)"
echo "empty_files=$(find "$TREE" -name '*.blame' -size 0 | wc -l)"
echo "size=$(du -sh "$TREE" | cut -f1)"
echo
echo "existing pre-C100 tree (untouched): $(du -sh "$DEST/blame" 2>/dev/null | cut -f1)"
echo
echo "parts kept at $PARTS -- delete once you are satisfied."
