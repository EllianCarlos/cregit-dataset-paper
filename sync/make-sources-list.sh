#!/usr/bin/env bash
# make-sources-list.sh: write sync/sources.tsv from sync/rules.tsv.
#
# Usage: sync/make-sources-list.sh SOURCE_ID COMMIT
#
# The script reads the file list of COMMIT in the source repository (git ls-tree).
# It does not read the working tree. It keeps the files that rules.tsv selects.
# It replaces the rows of SOURCE_ID in sources.tsv and keeps the rows of other sources.
# Review the diff of sources.tsv before you run sync-from-sources.sh.
#
# sources.local.conf gives the local clone and the path prefix of each source.
# That file is local only (see .gitignore), because it holds local paths.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
conf="$here/sources.local.conf"
rules="$here/rules.tsv"
out="$here/sources.tsv"

[ $# -eq 2 ] || { echo "usage: $0 SOURCE_ID COMMIT" >&2; exit 2; }
src=$1
rev=$2
[ -f "$conf" ] || { echo "error: $conf is missing (copy sources.local.conf.example)" >&2; exit 1; }

read -r repo prefix < <(awk -F'\t' -v s="$src" '$1 == s { print $2 "\t" $3 }' "$conf")
[ -n "${repo:-}" ] || { echo "error: source '$src' is not in $conf" >&2; exit 1; }
commit=$(git -C "$repo" rev-parse --verify "$rev^{commit}")

inc=$(awk -F'\t' -v s="$src" '$1 == s && $2 == "include" { printf "%s%s", sep, $3; sep = "|" }' "$rules")
exc=$(awk -F'\t' -v s="$src" '$1 == s && $2 == "exclude" { printf "%s%s", sep, $3; sep = "|" }' "$rules")
# The destination prefix: the "dest" rule of the source, else "pipeline/".
dest=$(awk -F'\t' -v s="$src" '$1 == s && $2 == "dest" { print $3; exit }' "$rules")
dest=${dest:-pipeline/}
[ -n "$inc" ] || { echo "error: no include rule for '$src'" >&2; exit 1; }

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
header='# source_id	source_commit	git_mode	git_blob	source_path	dest_path'
{
  echo "$header"
  if [ -f "$out" ]; then
    grep -v '^#' "$out" | awk -F'\t' -v s="$src" '$1 != s'
  fi
  # ls-tree output: "<mode> blob <oid>\t<path>". The path is relative to the prefix.
  git -C "$repo" ls-tree -r --full-tree "$commit:$prefix" |
    # Pass the patterns through ENVIRON: "awk -v" would change "\." into ".".
    INC="$inc" EXC="$exc" awk -F'\t' 'BEGIN { inc = ENVIRON["INC"]; exc = ENVIRON["EXC"] } {
      split($1, a, " ")
      if (a[2] != "blob") next
      if ($2 !~ inc) next
      if (exc != "" && $2 ~ exc) next
      print a[1] "\t" a[3] "\t" $2
    }' |
    awk -F'\t' -v s="$src" -v c="$commit" -v d="$dest" '{ print s "\t" c "\t" $1 "\t" $2 "\t" $3 "\t" d $3 }'
} > "$tmp"
# Sort the data rows by destination path. Keep the header first.
{ head -n 1 "$tmp"; tail -n +2 "$tmp" | LC_ALL=C sort -t "	" -k6,6; } > "$out"
n=$(grep -vc '^#' "$out")
echo "wrote $out: $n rows ($src at $commit)"
