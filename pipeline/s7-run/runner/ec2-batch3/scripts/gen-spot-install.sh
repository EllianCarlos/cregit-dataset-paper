#!/usr/bin/env bash
# gen-spot-install.sh: build spot-install-a.sh / spot-install-b.sh (files + parts init + identity check).
set -euo pipefail
cd "$(dirname "$0")"
F=(/usr/local/bin:census-steps)
for f in census-b3-parts-init census-b3-prep census-b3-check census-b3-start census-b3-run census-b3-upload census-b3-live census-b3-watch census-b3-finalize; do F+=("/usr/local/bin:../remote-spot/$f"); done
for f in census-b3@.service census-b3-finalize.service census-b3-live.service census-b3-live.timer census-b3-upload.service census-b3-upload.timer census-b3-watch.service; do F+=("/etc/systemd/system:../remote-spot/$f"); done
./mkinstall.sh spot-files.sh "${F[@]}"
cat > spot-post.sh <<'EOF'
set -uo pipefail
census-b3-parts-init "$X"
systemctl daemon-reload
cat /etc/cregit-census/batch.env
/usr/local/bin/census-b3-check
echo "check rc=$?"
EOF
for x in a b; do { cat spot-files.sh; echo "X=$x"; cat spot-post.sh; } > spot-install-$x.sh; bash -n spot-install-$x.sh; echo "spot-install-$x ok $(wc -c < spot-install-$x.sh) bytes"; done
