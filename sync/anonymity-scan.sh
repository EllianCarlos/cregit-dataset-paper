#!/usr/bin/env bash
# anonymity-scan.sh: find identifying text in the repository and write ANONYMIZATION-TODO.md.
#
# Usage: sync/anonymity-scan.sh
#
# The patterns come from sync/anonymity-patterns.local (local only, see the .example file).
# The report gives the kind, the file and the line number of each hit. It does not copy the
# matched text, so the report itself does not add identifying text.
# The script does not change any file other than ANONYMIZATION-TODO.md.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/.." && pwd)
pat="$here/anonymity-patterns.local"
out="$root/ANONYMIZATION-TODO.md"
[ -f "$pat" ] || { echo "error: $pat is missing (copy the .example file and fill it)" >&2; exit 1; }

hits=$(mktemp)
trap 'rm -f "$hits"' EXIT
cd "$root"
# All files that git would see, without .git and without the local-only files.
files=$( { git ls-files; git ls-files --others --exclude-standard; } | LC_ALL=C sort -u |
  grep -v -E '^(ANONYMIZATION-TODO\.md|sync/.*\.local)$' || true)

# One kind per line: the first pattern that matches wins.
kinds=$(grep -v '^#' "$pat" | cut -f1)
for kind in $kinds; do
  re=$(awk -F'\t' -v k="$kind" '$1 == k { print $2 }' "$pat")
  # grep -n -H: "file:line:text". Keep "file<TAB>line".
  echo "$files" | xargs -d '\n' grep -n -H -I -E -- "$re" 2>/dev/null |
    awk -v k="$kind" '{ i = index($0, ":"); f = substr($0, 1, i - 1); r = substr($0, i + 1);
      j = index(r, ":"); print k "\t" f "\t" substr(r, 1, j - 1) }' >> "$hits" || true
done
# Keep the first kind for each (file, line).
awk -F'\t' '!seen[$2 FS $3]++' "$hits" > "$hits.1" && mv "$hits.1" "$hits"

# The kind "census-name": the repository says "dataset", not "census". Copied scripts keep
# their identifiers for now. This pass lists each identifier that contains "census", in file
# contents and in file paths, for one rename pass later. It is separate from the kinds above,
# because a line can have an identifying hit and a census-name hit. The identifiers are not
# identifying text, so the report shows them.
cre='[A-Za-z0-9_./-]*[Cc][Ee][Nn][Ss][Uu][Ss][A-Za-z0-9_.-]*'
names=$(mktemp)
trap 'rm -f "$hits" "$names"' EXIT
# Skip project data: third-party project names such as "opencensus" are not our identifiers.
# So skip the data tables of the selection stages (S1 to S6, sources, rosters), and skip
# words that hold "opencensus" or "uscensus".
echo "$files" | grep -v -E '^pipeline/(s[1-6]-[a-z]+|sources|rosters)/.*\.(csv|tsv|jsonl|json)$' |
  xargs -d '\n' grep -o -H -I -E -- "$cre" 2>/dev/null |
  awk '{ i = index($0, ":"); print substr($0, i + 1) "\t" substr($0, 1, i - 1) }' |
  grep -v -i -E '^[^\t]*(opencensus|uscensus)' >> "$names" || true
echo "$files" | grep -E -- "$cre" | awk '{ print "(file path)\t" $0 }' >> "$names" || true

{
  echo "# Anonymization to-do list"
  echo
  echo "The review is double-blind. Before the repository goes to the anonymous mirror,"
  echo "remove or replace each hit below. sync/anonymity-scan.sh writes this file."
  echo "Do not edit it by hand. Run the script again after each fix."
  echo
  echo "The list gives the kind, the file and the line. It does not show the matched text."
  echo "The patterns are in sync/anonymity-patterns.local, which stays local."
  echo
  echo "Files under pipeline/ are copies. sync/sync-from-sources.sh checks their bytes."
  echo "So fix them in the source repository, commit there, and sync again."
  echo
  echo "## Count by kind"
  echo
  echo "| kind | files | lines |"
  echo "|---|---:|---:|"
  for kind in $kinds; do
    nf=$(awk -F'\t' -v k="$kind" '$1 == k { print $2 }' "$hits" | sort -u | wc -l)
    nl=$(awk -F'\t' -v k="$kind" '$1 == k' "$hits" | wc -l)
    echo "| $kind | $nf | $nl |"
  done
  nf=$(cut -f2 "$names" | sort -u | wc -l)
  ni=$(awk -F'\t' '$1 != "(file path)"' "$names" | wc -l)
  echo "| census-name | $nf | $ni occurrences |"
  echo
  echo "Kind census-name: identifiers and words that contain \"census\". The repository says"
  echo "\"dataset\" (stages: selection, build, merge, validate). Rename them later in one pass,"
  echo "in the source repositories. The section \"census-name\" below lists them."
  echo
  echo "## Items that the scan does not see"
  echo
  echo "- Git commit metadata: the author name and e-mail of each commit. The anonymous mirror"
  echo "  must serve files only, or the history must be rewritten in a fresh export."
  echo "- Hits in compressed files (*.xz, *.gz). The scan reads text files only."
  echo
  echo "## Hits"
  for kind in $kinds; do
    n=$(awk -F'\t' -v k="$kind" '$1 == k' "$hits" | wc -l)
    [ "$n" -gt 0 ] || continue
    echo
    echo "### $kind"
    echo
    awk -F'\t' -v k="$kind" '$1 == k { l[$2] = l[$2] (l[$2] == "" ? "" : ", ") $3 }
      END { for (f in l) print "- `" f "`: lines " l[f] }' "$hits" | LC_ALL=C sort
  done
  echo
  echo "### census-name"
  echo
  echo "File paths that contain \"census\":"
  echo
  awk -F'\t' '$1 == "(file path)" { print "- `" $2 "`" }' "$names" | LC_ALL=C sort -u
  echo
  echo "Identifiers and words in file contents (identifier: occurrences, files; more than 4 files gives the count only):"
  echo
  awk -F'\t' '$1 != "(file path)" { n[$1]++; if (!seen[$1 FS $2]++) { c[$1]++; f[$1] = f[$1] (f[$1] == "" ? "" : ", ") "`" $2 "`" } }
    END { for (k in n) print "- `" k "`: " n[k] ", " (c[k] > 4 ? c[k] " files" : f[k]) }' "$names" | LC_ALL=C sort
} > "$out"
echo "wrote $out: $(wc -l < "$hits") hit lines"
