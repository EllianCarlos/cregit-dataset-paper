# shellcheck shell=bash
# jv_batch.sh: the batches of an extra machine (sourced; bash).
# A batch is b-<seq>.tar.zst (the new .blame files), b-<seq>.list (their names) and
# b-<seq>.sha256 (of the tar.zst). formatBlame.pl writes each .blame to a temp file in the cregit
# build dir and renames it into the out dir (the same file system, checked by S1), so every
# *.blame in the out dir is complete. A batch takes only those names.
# The upload sends the .sha256 last: machine A takes a batch only when all 3 files exist.
# State files in ST: seq (last number), sent.list (names in committed batches), pending (the
# number of a batch that is built but not yet sent; it is sent again before a new one is built).

# jv_batch_build OUT ST BD: prints the seq of the batch to send (the pending one, or a new one),
# or nothing when there is no new file. Returns non-zero on an error.
jv_batch_build() {
  local out=$1 st=$2 bd=$3 n seq b
  if [ -s "$st/pending" ]; then cat "$st/pending"; return 0; fi
  touch "$st/sent.list" || return 1
  (cd "$out" && find . -type f -name '*.blame' -printf '%P\n') | LC_ALL=C sort > "$st/cur.list" || return 1
  LC_ALL=C sort -u "$st/sent.list" > "$st/sent.sorted" || return 1
  LC_ALL=C comm -23 "$st/cur.list" "$st/sent.sorted" > "$st/new.list" || return 1
  n=$(wc -l < "$st/new.list")
  [ "$n" -gt 0 ] || return 0
  seq=$(cat "$st/seq" 2>/dev/null || echo 0)
  seq=$(printf '%06d' $((10#$seq + 1)))
  b=$bd/b-$seq
  mkdir -p "$bd" || return 1
  tar -C "$out" --verbatim-files-from -T "$st/new.list" -cf - | zstd -q -T4 -3 -o "$b.tar.zst.tmp" -f
  local rc=("${PIPESTATUS[@]}")
  [ "${rc[0]}" = 0 ] && [ "${rc[1]}" = 0 ] || { rm -f "$b.tar.zst.tmp"; return 1; }
  mv -f "$b.tar.zst.tmp" "$b.tar.zst" && cp "$st/new.list" "$b.list" || return 1
  (cd "$bd" && sha256sum "b-$seq.tar.zst" > "b-$seq.sha256.tmp" && mv -f "b-$seq.sha256.tmp" "b-$seq.sha256") || return 1
  echo "$seq" > "$st/seq" && echo "$seq" > "$st/pending" || return 1
  echo "$seq"
}

# jv_batch_commit ST BD SEQ: after a full upload: the names count as sent, the batch files go.
jv_batch_commit() {
  local st=$1 bd=$2 seq=$3
  cat "$bd/b-$seq.list" >> "$st/sent.list" || return 1
  rm -f "$st/pending" "$bd/b-$seq.tar.zst" "$bd/b-$seq.sha256"
  mkdir -p "$bd/sent" && mv -f "$bd/b-$seq.list" "$bd/sent/"
}

# jv_batch_upload S3PART BD SEQ [AWS]: the tar.zst, the list, then the sha256.
jv_batch_upload() {
  local s3=$1 bd=$2 seq=$3 aws=${4:-aws} ext
  for ext in tar.zst list sha256; do
    "$aws" s3 cp "$bd/b-$seq.$ext" "$s3/batches/b-$seq.$ext" --only-show-errors || return 1
  done
}
