# t2-init.sh: the real part-init and identity check of a fed part on a TEST workload (batch99, part i1;
# test dirs, no census), then census-fed-upload and census-fed-finalize --dry-run on the check output.
# S3 objects: batch99/i1/done/ and batch99/i1/dryrun/<iid>/ (test objects, kept).
set +e
export AWS_PAGER=""
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag); X=$(. /etc/cregit-census/s5/batch.env; echo $HALF)
export FED_DIR=/etc/cregit-census/fedtest-init FED_INPUT=/home/ec2-user/fedtest-input
mkdir -p $FED_DIR $FED_INPUT/batch99; echo $X > $FED_DIR/half
printf 'half\tworkload\tpart\tworkers\tprojects\tpredicted_h\tsha256\n%s\tbatch99\ti1\t4\t1\t0.1\ttest\n' $X > $FED_INPUT/batch99/parts.batch99.tsv
echo "== $(date -u +%FT%TZ) $IID half $X; /data/cregit-ec2 $(du -sh /data/cregit-ec2 | cut -f1)"
/usr/local/bin/census-fed-workload batch99 --base
t0=$(date +%s); /usr/local/bin/census-fed-part-init batch99 i1; echo "part-init rc=$? ($(( $(date +%s) - t0 )) s)"
cat $FED_DIR/batch99i1.env | tr '\n' ' '; echo
t0=$(date +%s); /usr/local/bin/census-fed-check batch99i1 | tail -4; echo "check rc=${PIPESTATUS[0]} ($(( $(date +%s) - t0 )) s)"
. $FED_DIR/batch99i1.env
# a second env on the check output, for upload and finalize
sed -e "s#^ID=.*#ID=batch99i1#; s#^CTP=.*#CTP=$MP/ctp-check#; s#^OUT=.*#OUT=$MP/libexpat-check/out#; s#^LOG=.*#LOG=/data/logs/fed-check-batch99i1.log#" $FED_DIR/batch99i1.env > $FED_DIR/batch99i1.env.t && mv $FED_DIR/batch99i1.env.t $FED_DIR/batch99i1.env
cp /data/input/manifest.libexpat.tsv $FED_INPUT/batch99/manifest.batch99i1.tsv; cp /data/input/manifest.libexpat.tsv $FED_INPUT/batch99/manifest.batch99i1.run.tsv
chown -R ec2-user: $FED_INPUT; echo batch99i1 > $FED_DIR/started; chmod -R a+rX $FED_DIR
sudo -u ec2-user FED_DIR=$FED_DIR /usr/local/bin/census-fed-upload | cut -c1-160
aws s3 ls s3://${RUNNER_BUCKET}/batch99/i1/done/ --recursive | awk '{print $3, $4}' | cut -c1-120
/usr/local/bin/census-fed-finalize batch99i1 --dry-run 2>&1 | grep -E 'staged|check ok|DONE|dry run|FAILED|done/OK' | cut -c1-200
/usr/local/bin/census-fed-finalize batch99i1 --decide-only 2>&1 | tail -1 | cut -c1-200
echo "real fed dir: $(ls /etc/cregit-census/fed 2>&1 | head -1)  censuses: $(tr '\n' ' ' < /etc/cregit-census/censuses)"
systemctl is-active $(systemctl list-units --no-legend --plain 'census-b*@*.service' | awk '{print $1}') | sort | uniq -c
