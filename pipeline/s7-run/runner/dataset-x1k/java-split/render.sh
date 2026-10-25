#!/usr/bin/env bash
# render.sh [--check] (this machine): makes E1-export-a.sh, P1-install-a.sh and S1-setup-start.sh
# from src/*.body. ssm.sh sends one file, so each "#%EMBED <lib file> <target> <mode>" line becomes a
# gzip + base64 block that writes <lib file> to <target> on the machine, and checks its sha256 there.
# --check: renders to a temp dir and fails if a script differs from its body and lib files.
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd)
check=0; [ "${1:-}" = --check ] && check=1
out=$H; [ $check = 1 ] && out=$(mktemp -d)
for body in "$H"/src/*.body; do
  name=$(basename "$body" .body).sh
  python3 -I - "$H" "$body" > "$out/$name" <<'P'
import base64, gzip, hashlib, sys
h, body = sys.argv[1], sys.argv[2]
for line in open(body):
    if line.startswith("#%EMBED "):
        _, src, dest, mode = line.split()
        data = open(h + "/" + src, "rb").read()
        sha = hashlib.sha256(data).hexdigest()
        b64 = base64.encodebytes(gzip.compress(data, 9, mtime=0)).decode()
        print("# embedded %s (sha256 %s)" % (src, sha[:16]))
        print('mkdir -p "$(dirname "%s")"' % dest)
        print("base64 -d <<'EOF_JV_EMBED' | gunzip > \"%s.tmp\"" % dest)
        sys.stdout.write(b64)
        print("EOF_JV_EMBED")
        print('[ "$(sha256sum < "%s.tmp" | cut -d" " -f1)" = %s ] || { echo "ABORT: embedded %s sha256"; exit 1; }' % (dest, sha, src))
        print('chmod %s "%s.tmp" && mv -f "%s.tmp" "%s"' % (mode, dest, dest, dest))
    else:
        sys.stdout.write(line)
P
  bash -n "$out/$name"
  if [ $check = 1 ]; then
    cmp -s "$out/$name" "$H/$name" || { echo "render --check: $name is not up to date (run render.sh)"; rm -rf "$out"; exit 1; }
  fi
done
if [ $check = 1 ]; then rm -rf "$out"; echo "render --check: all up to date"; else echo "rendered: $(cd "$H/src" && ls ./*.body | sed 's#\./##; s/\.body$/.sh/' | tr '\n' ' ')"; fi
