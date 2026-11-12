#!/usr/bin/env bash
# J1-fs-jar-install.sh (the tom-fs1 machine, root, through ssm-fs.sh): installs the jar of cregit e1e7d94 over the jar of the AMI tree
# (backup kept), stops the unit ta-run (it sleeps after an ALERT), clears the ALERT and the work folder of the failed project
# (its memo holds only tokenizations of the first 17 minutes; the run tokenizes again from cold), and prints the state.
# Then start the run again with B1-fs-run.sh (the finished steps are skipped).
set -euo pipefail
WANT=7573dc66f91fd0cbcb92a26cebb0172e2f49f28f2c37dc0bc2bf9f7923b2c0cd
C=/data/ta/code/cregit/blobExec/target/scala-2.13/blobExec-0.1.0-assembly.jar
T=$(mktemp -d)
aws s3 cp s3://BUCKET_NAME/tom-fs1/jar/blobExec-e1e7d94-assembly.jar $T/j.jar --only-show-errors
[ "$(sha256sum $T/j.jar | cut -d' ' -f1)" = $WANT ] || { echo "ABORT: jar sha256"; exit 1; }
systemctl stop ta-run 2>/dev/null || true
[ -f $C.before-nullcommitter ] || cp -p $C $C.before-nullcommitter
install -o ec2-user -g ec2-user -m 644 $T/j.jar $C
echo "jar now: $(sha256sum $C | cut -c1-12) (before: $(sha256sum $C.before-nullcommitter | cut -c1-12))"
unzip -l $C | grep -c 'CommitIdents' | sed 's/^/classes of CommitIdents in the jar: /'
W=/data/ta/out/signalwire__freeswitch
if [ -d $W ]; then find $W -mindepth 1 -delete; rmdir $W; echo "work folder cleared"; fi
rm -f /data/ta/status/run.ALERT /data/ta/status/pass1.DONE
rm -rf $T 2>/dev/null || true
ls /data/ta/status; systemctl is-active ta-run || true
echo "J1-fs done"
