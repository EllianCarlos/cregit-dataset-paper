set +e
tail -n 25 /data/logs/batch3-b.log
journalctl -u census-b3@b.service -u census-b3-watch.service -u census-b3-upload.timer -u census-b3-live.timer -u census-b3-finalize.service --no-pager -n 30 -o short-iso | cut -c1-250
ls -la /data/ /home/ec2-user/ctp/STOP 2>&1 | head
tail -n 15 /data/logs/finalize.log
