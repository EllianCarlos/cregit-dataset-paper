#!/usr/bin/env bash
# spot-persons-db.sh (the user runs it; 2026-10-11, decision "persons.db: I run a script").
# Adds <project>-persons.db to the two spot uploaders, for the fed parts that still run:
#   census-fed-upload    (each finished project -> s3 <workload>/<part>/done/<name>/)
#   census-fed-finalize  (each part at its end -> s3 <workload>/<part>/final/<instance>/projects/<name>/)
# Steps:
#   1. Back up and patch the two local sources in ~/s3-work/ec2-batch6/scripts/remote-spot/.
#   2. Rebuild s6-files-0/1/2.sh (a relaunched spot installs the patched files).
#   3. On spot a and spot b: a read-only check that finished projects keep their persons.db,
#      then install only these two files (FILE.new, then mv; a running process keeps its old
#      inode; no unit is started, stopped, restarted or reloaded), then compare sha256 with the
#      local files.
# A project that was uploaded before the install keeps its done/ folder as it is (no backfill).
# Safe to run again: step 1 patches only once.
set -euo pipefail
export AWS_PROFILE=${RUNNER_AWS_PROFILE} AWS_REGION=${RUNNER_AWS_REGION} AWS_PAGER=""
RS=$HOME/s3-work/ec2-batch6/scripts/remote-spot
S6S=$HOME/s3-work/ec2-batch6/scripts
INST=$HOME/s3-work/ec2-batch3/instances.txt

# 1. patch the local sources (once)
[ -f $RS/census-fed-upload.orig-nopersons ] || cp -p $RS/census-fed-upload $RS/census-fed-upload.orig-nopersons
[ -f $RS/census-fed-finalize.orig-nopersons ] || cp -p $RS/census-fed-finalize $RS/census-fed-finalize.orig-nopersons
python3 - "$RS" <<'EOF'
import sys, pathlib
rs = pathlib.Path(sys.argv[1])
u = rs / "census-fed-upload"; s = u.read_text()
old = "        for f in (pq, stamp):\n            os.link(f, tmp / f.name)\n"
new = old + ("        persons = out / name / f\"{name}-persons.db\"  # 2026-10-11: also the persons DB\n"
             "        if persons.is_file():\n"
             "            os.link(persons, tmp / persons.name)\n")
if "persons = out / name" not in s:
    assert s.count(old) == 1, "census-fed-upload: anchor not found once"
    s = s.replace(old, new)
    s = s.replace("OUT/<name>/<name>.validated, ctp",
                  "OUT/<name>/<name>.validated, OUT/<name>/<name>-persons.db (if it exists), ctp", 1)
    u.write_text(s); print("patched census-fed-upload")
else:
    print("census-fed-upload: already patched")
f = rs / "census-fed-finalize"; s = f.read_text()
old = "-name '*.parquet' -o -name '*.validated' \\)"
new = "-name '*.parquet' -o -name '*.validated' -o -name '*-persons.db' \\)"
if new not in s:
    assert s.count(old) == 1, "census-fed-finalize: anchor not found once"
    f.write_text(s.replace(old, new)); print("patched census-fed-finalize")
else:
    print("census-fed-finalize: already patched")
EOF
python3 -m py_compile $RS/census-fed-upload && bash -n $RS/census-fed-finalize
diff $RS/census-fed-upload.orig-nopersons $RS/census-fed-upload || true
diff $RS/census-fed-finalize.orig-nopersons $RS/census-fed-finalize || true

# 2. rebuild the relaunch install scripts
(cd $S6S && ./gen-s6-files.sh)

# 3. check and install on both spots
WORK=$(mktemp -d)
cat > $WORK/install-persons.sh <<EOF
set -euo pipefail
echo "== \$(cat /sys/devices/virtual/dmi/id/board_asset_tag) half \$(cat /etc/cregit-census/fed/half 2>/dev/null)"
n=0; for e in /etc/cregit-census/fed/*.env; do . \$e; for d in \$OUT/*/; do nm=\$(basename \$d); [ -f \$d/\$nm.validated ] || continue
  n=\$((n+1)); [ \$n -le 3 ] && echo "check \$ID \$nm: \$(ls \$d | tr '\n' ' ')"; done; done
echo "finished projects on disk: \$n; with persons.db: \$(ls /w/*/census-*/*/*-persons.db 2>/dev/null | wc -l)"
EOF
for f in census-fed-upload census-fed-finalize; do
  { echo "cat > /usr/local/bin/$f.new <<'EOF_$f'"; cat $RS/$f; echo "EOF_$f"
    echo "chmod 755 /usr/local/bin/$f.new"; echo "mv -f /usr/local/bin/$f.new /usr/local/bin/$f"; } >> $WORK/install-persons.sh
done
echo 'sha256sum /usr/local/bin/census-fed-upload /usr/local/bin/census-fed-finalize' >> $WORK/install-persons.sh
bash -n $WORK/install-persons.sh
want=$(cd $RS && sha256sum census-fed-upload census-fed-finalize | awk '{print $1}' | tr '\n' ' ')
bad=0
for x in a b; do
  id=$(grep "^$x=" $INST | tail -1 | sed 's/^.=\([^ ]*\).*/\1/')
  echo "=== spot $x: $id"
  out=$(cd $S6S && I=$id TAILN=40 ./ssm.sh $WORK/install-persons.sh 600) || { echo "$out"; echo "spot $x: SSM FAILED"; bad=1; continue; }
  echo "$out"
  got=$(echo "$out" | grep -E '/usr/local/bin/census-fed-(upload|finalize)$' | awk '{print $1}' | tr '\n' ' ')
  [ "$got" = "$want" ] && echo "spot $x: installed, sha256 equal to the local files" || { echo "spot $x: SHA256 MISMATCH (want $want got $got)"; bad=1; }
done
rm -rf "$WORK"
[ $bad = 0 ] && echo "ALL OK" || echo "SOME STEPS FAILED"
