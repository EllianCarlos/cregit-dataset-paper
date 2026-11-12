#!/usr/bin/env bash
# J2-fs-fix2-install.sh (the tom-fs1 machine, root, through ssm-fs.sh): the second repair. Stops the sleeping unit, takes the new stage
# (WANT_SUMS 1f88e9dc2b7c) into /data/ta/tools, installs the jars of slickGitLog and persons (cregit c879bd3) over the AMI jars (backups kept),
# puts the cregit tree at c879bd3, clears the ALERT. The work folder of the project (tokenize done, memo) is NOT touched.
# Then: B1-fs-run.sh with EXPORTS="GROUP=bulk PASS1_FROM_STEP=3".
set -euo pipefail
export HOME=${HOME:-/root}
WANT=1f88e9dc2b7c426fbaa038ef0438b11fa2c8c6538299adbd410fb11f691a8d06; SL=7fde5a036e243fb9ab46198caa18a68e7dac3e7b83c7e7b1b63af377f9a167eb; PE=7939aa17590d4f0c294dacafc960cb610b3341f338944c433cc947e4d269067a
B=s3://BUCKET_NAME/tom-fs1; T=/data/ta/tools; C=/data/ta/code/cregit
systemctl stop ta-run 2>/dev/null || true
aws s3 sync $B/tools/ $T/ --delete --exact-timestamps --only-show-errors
[ "$(sha256sum $T/SHA256SUMS | cut -d' ' -f1)" = $WANT ] || { echo "ABORT: tools/SHA256SUMS is not ${WANT:0:12}"; exit 1; }
(cd $T && sha256sum --quiet -c SHA256SUMS) || { echo "ABORT: a tool sha256"; exit 1; }
echo "tools ok: $(wc -l < $T/SHA256SUMS) files"
Tm=$(mktemp -d)
aws s3 cp $B/jar2/ $Tm/ --recursive --only-show-errors
[ "$(sha256sum $Tm/slickgitlog_2.10-0.1-SNAPSHOT-one-jar.jar | cut -d' ' -f1)" = $SL ] && [ "$(sha256sum $Tm/persons_2.10-0.1-SNAPSHOT-one-jar.jar | cut -d' ' -f1)" = $PE ] || { echo "ABORT: jar sha256"; exit 1; }
for m in slickGitLog:slickgitlog persons:persons; do
  d=${m%%:*}; n=${m##*:}; J=$C/$d/target/scala-2.10/${n}_2.10-0.1-SNAPSHOT-one-jar.jar
  [ -f $J.before-nullcommitter ] || cp -p $J $J.before-nullcommitter
  install -o ec2-user -g ec2-user -m 644 $Tm/${n}_2.10-0.1-SNAPSHOT-one-jar.jar $J
  echo "$d jar now $(sha256sum $J | cut -c1-12)"
done
sudo -u ec2-user git -c safe.directory='*' -C $C fetch -q $T/code/cregit-ta.bundle fix/null-committer
sudo -u ec2-user git -c safe.directory='*' -C $C checkout -q  2>&1 | tail -2 || true
echo "cregit HEAD: $(sudo -u ec2-user git -c safe.directory='*' -C $C rev-parse --short HEAD)"
touch $C/blobExec/target/scala-2.13/*.jar $C/slickGitLog/target/scala-2.10/*one-jar.jar $C/persons/target/scala-2.10/*one-jar.jar
rm -f /data/ta/status/run.ALERT /data/ta/status/pass1.DONE
rm -rf $Tm
systemctl is-active ta-run || true; ls /data/ta/status
echo "J2-fs done"
