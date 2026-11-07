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
# patches.tsv lists copied files that hold a value that must not be published (for example the
# name of the private study repository in a default path). Each row replaces one line of one
# copied file. The copy step first checks the git blob id of the file as it came from the source
# (the file that ran), then replaces the line. The check compares the sha256 of the result with
# the value of patches.tsv. The replaced text is not in this repository, so only a reader of the
# source repository can check the file that ran; tools.lock gives its sha256.
#
# sources.local.conf gives the local clone and the path prefix of each source.
# The --check mode does not need that file.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)
conf="$here/sources.local.conf"
list="$here/sources.tsv"
ulist="$here/untracked.tsv"
plist="$here/patches.tsv"
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

  # The line replacements of patches.tsv. Columns: dest_path, line number, sha256 after, new line.
  if [ -f "$plist" ]; then
    np=0
    while IFS=$'\t' read -r dest line want text; do
      f="$root/$dest"
      blob=$(grep -v '^#' "$list" | awk -F'\t' -v d="$dest" '$6 == d { print $4 }')
      got=$(git hash-object --no-filters -- "$f")
      if [ "$got" = "$blob" ]; then
        TEXT="$text" awk -v n="$line" 'NR == n { print ENVIRON["TEXT"]; next } { print }' "$f" > "$f.patch-tmp"
        chmod --reference="$f" "$f.patch-tmp" && mv "$f.patch-tmp" "$f"
      fi
      got=$(sha256sum < "$f" | cut -d' ' -f1)
      [ "$got" = "$want" ] || { echo "error: $dest: sha256 $got after the patch, patches.tsv says $want" >&2; exit 1; }
      np=$((np + 1))
    done < <(grep -v '^#' "$plist")
    echo "patched $np lines (sha256 checked)"
  fi

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
# A patched file (patches.tsv): its sha256 must be the value of patches.tsv.
patched() { [ -f "$plist" ] && awk -F'\t' -v d="$1" '!/^#/ && $1 == d { w = $3; f = 1 } END { if (f) print w; exit !f }' "$plist"; }
while IFS=$'\t' read -r gmode blob dest; do
  f="$root/$dest"
  if [ ! -f "$f" ]; then echo "MISSING $dest"; fail=1; continue; fi
  if want=$(patched "$dest"); then
    got=$(sha256sum < "$f" | cut -d' ' -f1)
    [ "$got" = "$want" ] || { echo "CHANGED $dest (sha256 $got, patches.tsv says $want)"; fail=1; }
    if [ "$gmode" = 100755 ] && [ ! -x "$f" ]; then echo "MODE $dest (want 100755)"; fail=1; fi
    if [ "$gmode" = 100644 ] && [ -x "$f" ]; then echo "MODE $dest (want 100644)"; fail=1; fi
    continue
  fi
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
# The destination directories: the destination prefix of each row (dest_path without source_path).
# All of pipeline/ counts as one directory.
tops=$(grep -v '^#' "$list" | awk -F'\t' '{ p = substr($6, 1, length($6) - length($5)); sub(/\/$/, "", p)
  if (p ~ /^pipeline(\/|$)/) p = "pipeline"; print p }' | LC_ALL=C sort -u)
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
