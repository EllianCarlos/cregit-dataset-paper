# left-out.sh: source it. left_out PATH is true when PATH (relative to the repository) matches an
# export-ignore line of .gitattributes: a file that the Zenodo zip of the package leaves out.
# The checks use it only for a file that is missing, so a full checkout checks every file.
_lo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
_lo_pats=$(awk '$NF == "export-ignore" { p = $1; sub(/^\//, "", p); gsub(/\*\*/, "*", p); print p }' "$_lo_root/.gitattributes" 2>/dev/null || true)
left_out() {
  local p pat
  p=$1
  while IFS= read -r pat; do
    [ -n "$pat" ] || continue
    # shellcheck disable=SC2053
    [[ $p == $pat ]] && return 0
  done <<< "$_lo_pats"
  return 1
}
