# shellcheck shell=bash
# jv_gate.sh: the gate compare of an extra machine (sourced; bash).
# jv_gate_compare LIST ADIR XDIR RESULT
#   LIST: "size<TAB>name" per gate file. ADIR: machine A's .blame files. XDIR: the .blame files
#   made here. Each pair is compared byte for byte (cmp). RESULT gets one line per file:
#   "<n> OK|DIFF|NO-A|NO-HERE <sha256 of A, 16> <sha256 here, 16> <name>".
#   Stdout: one line "gate: <ok> equal, <bad> not equal of <n>" (no names).
#   Returns 0 only when every file is equal and the list has at least one file.
jv_gate_compare() {
  local list=$1 adir=$2 xdir=$3 res=$4 n=0 ok=0 bad=0 name a x st sa sx
  : > "$res" || return 2
  while IFS=$'\t' read -r _ name; do
    [ -n "$name" ] || continue
    n=$((n + 1)); a="$adir/$name.blame"; x="$xdir/$name.blame"
    sa=-; sx=-
    [ -f "$a" ] && sa=$(sha256sum < "$a" | cut -c1-16)
    [ -f "$x" ] && sx=$(sha256sum < "$x" | cut -c1-16)
    if [ ! -f "$a" ]; then st=NO-A
    elif [ ! -f "$x" ]; then st=NO-HERE
    elif cmp -s -- "$a" "$x"; then st=OK
    else st=DIFF; fi
    [ "$st" = OK ] && ok=$((ok + 1)) || bad=$((bad + 1))
    printf '%d %s %s %s %s\n' "$n" "$st" "$sa" "$sx" "$name" >> "$res"
  done < "$list"
  echo "gate: $ok equal, $bad not equal of $n"
  [ "$n" -gt 0 ] && [ "$bad" = 0 ]
}
