#!/usr/bin/env bash
# S1-feed-line.sh (this machine; after upload-batch23.sh printed ALL OK): append the batch23 line of
# feed.next.tsv to ~/s3-work/ec2-batch6/feed.tsv (read by restart_spot.sh on a relaunch and by the
# watchdog), so that a relaunched spot sets the batch23 commit (57551d7) and queues its parts. The old
# file is kept as feed.tsv.bak.<epoch>; temp file and atomic mv.
set -euo pipefail
D=$HOME/s3-work/ec2-batch6
line=$(grep -P '^batch23\t' $D/feed.next.tsv)
[ "$(echo "$line" | cut -f3)" = 57551d7ad82a784615c1490623d72cb9dc994ba1 ] || { echo "ABORT: feed.next.tsv batch23 line"; exit 1; }
grep -qP '^batch23\t' $D/feed.tsv && { echo "feed.tsv has batch23 already: nothing changed"; exit 0; }
cp -p $D/feed.tsv $D/feed.tsv.bak.$(date +%s)
t=$(mktemp $D/feed.tsv.XXXX); { cat $D/feed.tsv; echo "$line"; } > $t; chmod 644 $t; mv -f $t $D/feed.tsv
echo "feed.tsv: $(grep -c '^batch' $D/feed.tsv) workloads; last: $(tail -1 $D/feed.tsv | cut -c1-110)"
bash ~/s3-work/ec2-batch3/restart_spot.sh --remaining a; bash ~/s3-work/ec2-batch3/restart_spot.sh --remaining b
