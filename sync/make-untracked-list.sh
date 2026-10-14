#!/usr/bin/env bash
# make-untracked-list.sh: write sync/untracked.tsv, the list of generated inputs that git
# does not track in the source repository, but that a committed checksum file records.
#
# Usage: sync/make-untracked-list.sh SOURCE_ID COMMIT PATTERN CHECKSUM_FILE...
#   PATTERN        an extended regular expression on the file name (for example
#                  '^(frame|project_meta)\.').
#   CHECKSUM_FILE  a file in "sha256sum" format, tracked at COMMIT, with its path
#                  relative to the source prefix (for example s7-run/SHA256SUMS).
#
# The script reads each checksum file from COMMIT (git show), not from the working tree.
# So the sha256 of each row comes from a commit. sync-from-sources.sh copies the file
# from the working tree only when its sha256 is equal to that value.
# Rows with a path outside the directory of the checksum file ("../") are skipped.
# The script replaces the rows of SOURCE_ID in untracked.tsv.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
conf="$here/sources.local.conf"
out="$here/untracked.tsv"
[ $# -ge 4 ] || { echo "usage: $0 SOURCE_ID COMMIT PATTERN CHECKSUM_FILE..." >&2; exit 2; }
src=$1; rev=$2; pat=$3; shift 3
[ -f "$conf" ] || { echo "error: $conf is missing" >&2; exit 1; }
read -r repo prefix < <(awk -F'\t' -v s="$src" '$1 == s { print $2 "\t" $3 }' "$conf")
[ -n "${repo:-}" ] || { echo "error: source '$src' is not in $conf" >&2; exit 1; }
commit=$(git -C "$repo" rev-parse --verify "$rev^{commit}")

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
{
  echo "# source_id	source_commit	checksum_file	sha256	source_path	dest_path"
  if [ -f "$out" ]; then grep -v '^#' "$out" | awk -F'\t' -v s="$src" '$1 != s'; fi
  for sums in "$@"; do
    dir=$(dirname "$sums")
    git -C "$repo" show "$commit:${prefix:+$prefix/}$sums" |
      PAT="$pat" awk -v s="$src" -v c="$commit" -v f="$sums" -v d="$dir" '
        BEGIN { pat = ENVIRON["PAT"] }
        /^[0-9a-f]{64}  / {
          h = substr($0, 1, 64); p = substr($0, 67)
          if (p ~ /^\.\.\// || p ~ /\//) next
          if (p !~ pat) next
          print s "\t" c "\t" f "\t" h "\t" d "/" p "\tpipeline/" d "/" p
        }'
  done
} > "$tmp"
{ head -n 1 "$tmp"; tail -n +2 "$tmp" | LC_ALL=C sort -t "	" -k6,6 -u; } > "$out"
echo "wrote $out: $(grep -vc '^#' "$out") rows ($src at $commit)"
