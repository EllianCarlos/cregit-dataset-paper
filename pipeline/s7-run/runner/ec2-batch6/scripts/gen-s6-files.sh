#!/usr/bin/env bash
# gen-s6-files.sh: build s6-files-0.sh, -1.sh and -2.sh (run in that order), the install scripts of the fed spot files
# (remote-spot/), each file written to FILE.new and then renamed (a reader, or a running bash, never
# sees half a file; a running script keeps its old inode). s6-files-2.sh also replaces
# census-spot-decide (with the fed word; the batch 5 version is kept as census-spot-decide.orig-b3b5)
# and, after checking NeedDaemonReload=no on every loaded census unit, runs daemon-reload (no unit is
# started, stopped or restarted).
set -euo pipefail
cd "$(dirname "$0")"
bins0="census-fed-common census-fed-derive census-fed-enqueue census-fed-workload census-fed-run"
bins1="census-fed-part-init census-fed-check census-fed-feeder census-fed-finalize"
bins2="census-fed-upload census-fed-live census-fed-trim census-fed-watch census-spot-decide"
units="census-fed@.service census-fed-finalize@.service census-fed-feeder.service census-fed-feeder.timer census-fed-upload.service census-fed-upload.timer census-fed-live.service census-fed-live.timer census-fed-watch.service"
emit() { for f in "$@"; do echo "cat > /usr/local/bin/$f.new <<'EOF_$f'"; cat remote-spot/$f; echo "EOF_$f"; echo "chmod 755 /usr/local/bin/$f.new"; echo "mv -f /usr/local/bin/$f.new /usr/local/bin/$f"; done; }
# units: replaced (and a daemon-reload done) only if their content changed
emitu() { echo 'uchanged=0'; for f in "$@"; do echo "cat > /etc/systemd/system/$f.new <<'EOF_$f'"; cat remote-spot/$f; echo "EOF_$f"; echo "chmod 644 /etc/systemd/system/$f.new"; echo "if cmp -s /etc/systemd/system/$f.new /etc/systemd/system/$f; then rm -f /etc/systemd/system/$f.new; else mv -f /etc/systemd/system/$f.new /etc/systemd/system/$f; uchanged=1; fi"; done; }
{ echo 'set -euo pipefail'; emit $bins0; echo 'echo "s6 files 0 installed"'; } > s6-files-0.sh
{ echo 'set -euo pipefail'; emit $bins1; echo 'echo "s6 files 1 installed"'; } > s6-files-1.sh
{ echo 'set -euo pipefail'
  echo '[ -e /usr/local/bin/census-spot-decide.orig-b3b5 ] || cp -p /usr/local/bin/census-spot-decide /usr/local/bin/census-spot-decide.orig-b3b5'
  emit $bins2; emitu $units
  echo 'if [ $uchanged = 0 ]; then echo "unit files unchanged: no daemon-reload"; else'
  echo 'for u in $(systemctl list-units --no-legend --plain --all "census*" | awk "{print \$1}"); do [ "$(systemctl show $u -p NeedDaemonReload --value)" = no ] || { echo "$u: NeedDaemonReload=yes; no daemon-reload"; exit 1; }; done'
  echo 'before=$(for u in $(systemctl list-units --no-legend --plain "census-b*@*.service" | awk "{print \$1}"); do echo "$u $(systemctl show $u -p MainPID -p ActiveEnterTimestamp --value | tr "\n" " ")"; done)'
  echo 'systemctl daemon-reload'
  echo 'after=$(for u in $(systemctl list-units --no-legend --plain "census-b*@*.service" | awk "{print \$1}"); do echo "$u $(systemctl show $u -p MainPID -p ActiveEnterTimestamp --value | tr "\n" " ")"; done)'
  echo '[ "$before" = "$after" ] && echo "running census units unchanged by daemon-reload ($(echo "$before" | grep -c .) units)" || { echo "CHANGED:"; diff <(echo "$before") <(echo "$after"); }'
  echo 'fi'
  echo 'echo "s6 files 2 installed: $(sha256sum /usr/local/bin/census-spot-decide /usr/local/bin/census-fed-feeder /usr/local/bin/census-fed-finalize | cut -c1-12 | tr "\n" " ")"'
} > s6-files-2.sh
for f in s6-files-0.sh s6-files-1.sh s6-files-2.sh; do bash -n $f; echo "$f $(wc -c < $f) bytes"; done
