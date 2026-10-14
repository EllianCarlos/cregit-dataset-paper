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
# git_blob column. It also lists files under the destination directories that
# sources.tsv does not list. It does not delete them. Delete them yourself after a review.
#
# untracked.tsv lists generated inputs that git does not track in the source. The script
# copies them from the source working tree, but only when the sha256 is equal to the value
# in a committed checksum file (see make-untracked-list.sh). The check compares the sha256.
#
# sources.local.conf gives the local clone and the path prefix of each source.
# The --check mode does not need that file.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)
conf="$here/sources.local.conf"
list="$here/sources.tsv"
ulist="$here/untracked.tsv"
mode=copy
[ "${1:-}" = "--check" ] && mode=check

if [ "$mode" = copy ]; then
  [ -f "$conf" ] || { echo "error: $conf is missing (copy sources.local.conf.example)" >&2; exit 1; }
  # One "git archive" for each (source_id, source_commit) pair.
  grep -v '^#' "$list" | cut -f1,2 | sort -u | while IFS=$'\t' read -r src commit; do
    read -r repo prefix < <(awk -F'\t' -v s="$src" '$1 == s { print $2 "\t" $3 }' "$conf")
    [ -n "${repo:-}" ] || { echo "error: source '$src' is not in $conf" >&2; exit 1; }
    git -C "$repo" cat-file -e "$commit^{commit}" || { echo "error: $src has no commit $commit" >&2; exit 1; }
    # All rows of this pair must have one destination prefix: dest_path = prefix + source_path.
    dests=$(grep -v '^#' "$list" | awk -F'\t' -v s="$src" -v c="$commit" '$1 == s && $2 == c {
      n = length($6) - length($5); if (n < 1 || substr($6, n + 1) != $5) print "BAD"; else print substr($6, 1, n) }' | sort -u)
    [ "$(echo "$dests" | wc -l)" -eq 1 ] && [ "$dests" != BAD ] ||
      { echo "error: $src at $commit has no single destination prefix" >&2; exit 1; }
    paths=$(mktemp)
    grep -v '^#' "$list" | awk -F'\t' -v s="$src" -v c="$commit" '$1 == s && $2 == c { print $5 }' > "$paths"
    mkdir -p "$root/$dests"
    # "commit:prefix" makes the archive paths relative to the prefix.
    # xargs keeps the command line short. Each call writes a complete tar stream.
    (cd "$repo" && xargs -d '\n' git archive --format=tar "$commit:$prefix" --) < "$paths" |
      tar -x -i -C "$root/$dests" -f -
    echo "copied $(wc -l < "$paths") files of $src at $commit"
    rm -f "$paths"
  done

  # Generated inputs that git does not track (untracked.tsv). Copy each one from the
  # working tree of the source only when its sha256 equals the value of the committed
  # checksum file.
  if [ -f "$ulist" ]; then
    n=0
    while IFS=$'\t' read -r src commit sums want spath dest; do
      read -r repo prefix < <(awk -F'\t' -v s="$src" '$1 == s { print $2 "\t" $3 }' "$conf")
      f="$repo/${prefix:+$prefix/}$spath"
      [ -f "$f" ] || { echo "error: $f is missing in the source working tree" >&2; exit 1; }
      got=$(sha256sum < "$f" | cut -d' ' -f1)
      [ "$got" = "$want" ] || { echo "error: $spath has sha256 $got, $sums at $commit says $want" >&2; exit 1; }
      mkdir -p "$(dirname "$root/$dest")"
      install -m 644 "$f" "$root/$dest"
      n=$((n + 1))
    done < <(grep -v '^#' "$ulist")
    echo "copied $n untracked files (sha256 checked)"
  fi
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

# Check: sha256 of every file of untracked.tsv.
utmp=$(mktemp)
trap 'rm -f "$tmp" "$utmp"' EXIT
if [ -f "$ulist" ]; then grep -v '^#' "$ulist" | cut -f4,6 > "$utmp"; fi
while IFS=$'\t' read -r want dest; do
  f="$root/$dest"
  if [ ! -f "$f" ]; then echo "MISSING $dest"; fail=1; continue; fi
  got=$(sha256sum < "$f" | cut -d' ' -f1)
  if [ "$got" != "$want" ]; then echo "CHANGED $dest (sha256 $got, want $want)"; fail=1; fi
done < "$utmp"

# Report files under the destination directories that the two lists do not name.
tops=$(cut -f3 "$tmp" | cut -d/ -f1-2 | sed -E 's#^(pipeline)/.*#\1#' | LC_ALL=C sort -u)
# Files that .gitignore names (for example __pycache__/) do not count.
extra=$(cd "$root" && git ls-files --cached --others --exclude-standard -- $tops | LC_ALL=C sort -u |
  LC_ALL=C comm -23 - <( { cut -f3 "$tmp"; cut -f2 "$utmp"; } | LC_ALL=C sort))
if [ -n "$extra" ]; then
  echo "NOT LISTED (review, then delete or add a rule):"
  echo "$extra" | sed 's/^/  /'
  fail=1
fi

n=$(wc -l < "$tmp"); u=$(wc -l < "$utmp")
if [ "$fail" -eq 0 ]; then echo "OK: $n files match sources.tsv, $u files match untracked.tsv"; else echo "FAIL: see the lines above"; exit 1; fi
