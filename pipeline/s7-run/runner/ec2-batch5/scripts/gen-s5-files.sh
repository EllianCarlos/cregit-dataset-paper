#!/usr/bin/env bash
# gen-s5-files.sh: build s5-files.sh, the install script of the batch5 / batch1rest spot files
# (remote-spot/), each written to FILE.new and then renamed (a reader, or a running bash, never sees
# half a file; a running script keeps its old inode). Includes the patched census-b3-finalize.
set -euo pipefail
cd "$(dirname "$0")"
units="census-b5@.service census-b5-finalize.service census-b5-live.service census-b5-live.timer census-b5-upload.service census-b5-upload.timer census-b5-watch.service"
emit() { for f in "$@"; do echo "cat > /usr/local/bin/$f.new <<'EOF_$f'"; cat remote-spot/$f; echo "EOF_$f"; echo "chmod 755 /usr/local/bin/$f.new"; echo "mv -f /usr/local/bin/$f.new /usr/local/bin/$f"; done; }
emitu() { for f in "$@"; do echo "cat > /etc/systemd/system/$f.new <<'EOF_$f'"; cat remote-spot/$f; echo "EOF_$f"; echo "chmod 644 /etc/systemd/system/$f.new"; echo "mv -f /etc/systemd/system/$f.new /etc/systemd/system/$f"; done; }
# two scripts (an SSM command has a size limit): 1 = derive, parts-init, prep, check, start, run, upload;
# 2 = the rest, the units and the patched census-b3-finalize (its original kept as .orig-b3only).
{ echo 'set -euo pipefail'; emit census-b5-derive census-b5-parts-init census-b5-prep census-b5-check census-b5-start census-b5-run census-b5-upload; } > s5-files-1.sh
{ echo 'set -euo pipefail'
  echo '[ -e /usr/local/bin/census-b3-finalize.orig-b3only ] || cp -p /usr/local/bin/census-b3-finalize /usr/local/bin/census-b3-finalize.orig-b3only'
  emit census-b5-live census-b5-trim census-b5-watch census-b5-finalize census-spot-decide census-b3-finalize; emitu $units
  echo 'echo "s5 files installed: $(sha256sum /usr/local/bin/census-b3-finalize /usr/local/bin/census-spot-decide /usr/local/bin/census-b5-finalize | cut -c1-12 | tr "\n" " ")"'
} > s5-files-2.sh
cat s5-files-1.sh s5-files-2.sh > s5-files.sh  # for restore-<x>.sh (one script per relaunch is split there too)
for f in s5-files-1.sh s5-files-2.sh; do bash -n $f; echo "$f $(wc -c < $f) bytes"; done
