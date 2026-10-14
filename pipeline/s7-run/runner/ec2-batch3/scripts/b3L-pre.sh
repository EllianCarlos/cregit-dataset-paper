set -euo pipefail
B=/usr/local/bin
cur=$(sha256sum $B/census-batch2-finalize | cut -d' ' -f1)
[ -e $B/census-batch2-finalize.orig-20261009 ] || { [ "$cur" = 05739809c2d456613ba58c994e80eb2fd73cd27d4a98a947748a29f8a27664db ] || { echo "census-batch2-finalize is not the expected version ($cur)"; exit 1; }; cp -p $B/census-batch2-finalize $B/census-batch2-finalize.orig-20261009; }
echo "batch2 finalize backed up; census-batch2: $(systemctl is-active census-batch2.service)"
