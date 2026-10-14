#!/usr/bin/env bash
# sync-from-sources.sh: copy the files that sync/sources.tsv lists into this repository.
#
# Usage:
#   sync/sync-from-sources.sh           copy, then check
#   sync/sync-from-sources.sh --check   check only (no copy)
#
# The script reads each file from the recorded source commit with "git archive".
# It does not read the working tree of the source repository. So a later run with
# the same sources.tsv gives the same bytes.
# After the copy, the script checks each file: its git blob id must be equal to the
# git_blob column. It also lists files under pipeline/ that sources.tsv does not
# list. It does not delete them. Delete them yourself after a review.
#
# sources.local.conf gives the local clone and the path prefix of each source.
# The --check mode does not need that file.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)
conf="$here/sources.local.conf"
list="$here/sources.tsv"
mode=copy
[ "${1:-}" = "--check" ] && mode=check

if [ "$mode" = copy ]; then
  [ -f "$conf" ] || { echo "error: $conf is missing (copy sources.local.conf.example)" >&2; exit 1; }
  # One "git archive" for each (source_id, source_commit) pair.
  grep -v '^#' "$list" | cut -f1,2 | sort -u | while IFS=$'\t' read -r src commit; do
    read -r repo prefix < <(awk -F'\t' -v s="$src" '$1 == s { print $2 "\t" $3 }' "$conf")
    [ -n "${repo:-}" ] || { echo "error: source '$src' is not in $conf" >&2; exit 1; }
    git -C "$repo" cat-file -e "$commit^{commit}" || { echo "error: $src has no commit $commit" >&2; exit 1; }
    # All rows of this pair must have the same destination prefix ("pipeline/" + source_path).
    bad=$(grep -v '^#' "$list" | awk -F'\t' -v s="$src" -v c="$commit" \
      '$1 == s && $2 == c && $6 != "pipeline/" $5' | head -n 1)
    [ -z "$bad" ] || { echo "error: unexpected dest_path in row: $bad" >&2; exit 1; }
    paths=$(mktemp)
    grep -v '^#' "$list" | awk -F'\t' -v s="$src" -v c="$commit" '$1 == s && $2 == c { print $5 }' > "$paths"
    mkdir -p "$root/pipeline"
    # "commit:prefix" makes the archive paths relative to the prefix.
    # xargs keeps the command line short. Each call writes a complete tar stream.
    (cd "$repo" && xargs -d '\n' git archive --format=tar "$commit:$prefix" --) < "$paths" |
      tar -x -i -C "$root/pipeline" -f -
    echo "copied $(wc -l < "$paths") files of $src at $commit"
    rm -f "$paths"
  done
fi

# Check: git blob id and file mode of every listed file.
fail=0
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
grep -v '^#' "$list" | cut -f3,4,6 > "$tmp"
while IFS=$'\t' read -r gmode blob dest; do
  f="$root/$dest"
  if [ ! -f "$f" ]; then echo "MISSING $dest"; fail=1; continue; fi
  got=$(git hash-object --no-filters -- "$f")
  if [ "$got" != "$blob" ]; then echo "CHANGED $dest (blob $got, want $blob)"; fail=1; fi
  if [ "$gmode" = 100755 ] && [ ! -x "$f" ]; then echo "MODE $dest (want 100755)"; fail=1; fi
  if [ "$gmode" = 100644 ] && [ -x "$f" ]; then echo "MODE $dest (want 100644)"; fail=1; fi
done < "$tmp"

# Report files under pipeline/ that sources.tsv does not list.
extra=$(cd "$root" && find pipeline -type f | LC_ALL=C sort |
  LC_ALL=C comm -23 - <(cut -f3 "$tmp" | LC_ALL=C sort))
if [ -n "$extra" ]; then
  echo "NOT LISTED (review, then delete or add a rule):"
  echo "$extra" | sed 's/^/  /'
  fail=1
fi

n=$(wc -l < "$tmp")
if [ "$fail" -eq 0 ]; then echo "OK: $n files match sources.tsv"; else echo "FAIL: see the lines above"; exit 1; fi
