#!/usr/bin/env bash
# mkinstall.sh OUT DEST_DIR:FILE... : write an install script that puts each remote/FILE at
# DEST_DIR/FILE (written to FILE.new, then renamed, so a reader never sees half a file).
set -euo pipefail
out=$1; shift
{ echo 'set -euo pipefail'
  for spec in "$@"; do dir=${spec%%:*}; f=${spec#*:}; b=$(basename "$f")
    echo "cat > $dir/$b.new <<'EOF_$b'"; cat "remote/$f"; echo "EOF_$b"
    case $b in *.service|*.timer) echo "chmod 644 $dir/$b.new" ;; *) echo "chmod 755 $dir/$b.new" ;; esac
    echo "mv -f $dir/$b.new $dir/$b"
  done; } > "$out"
