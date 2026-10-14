# The 7 projects terminated at 13:39 cannot resume at step 2 on the per-part cregit copy: blobExec
# refuses an incremental run when the recorded tokenizer command path differs
# (/data/cregit-ec2/... vs /b4pK/cregit-ec2/...). Move their work dirs aside so their queued retry
# starts from step 1. Only if the project is not running now.
set +e
R=/data/logs/batch4-restart-20261009.txt
echo "== $(date -u +%FT%TZ) work dirs moved to <out>/.superseded-20261009/ (blob_map meta mismatch on resume)" >> $R
for spec in 1:net-snmp__net-snmp 1:CrispStrobe__CrispASR 2:rism-digital__verovio 2:projectacrn__acrn-libvirt 2:apache__camel-spring-boot 3:kovidgoyal__kitty 3:peercoin__peercoin; do
  k=${spec%%:*}; n=${spec#*:}; O=/b4p$k/census-2026-10-batch4
  last=$(grep "\"project\": \"$n\"" /b4p$k/ctp/ledger.jsonl | tail -1 | python3 -c 'import json,sys; r=json.loads(sys.stdin.read() or "{}"); print(r.get("step"), r.get("status"), r.get("state"))')
  run=$(pgrep -f "$O/$n" | wc -l)
  hold=$(grep -c "$n ▶ pipeline started" /data/logs/batch4p$k.log)
  if [ "$run" = 0 ] && [ -d "$O/$n" ]; then
    mkdir -p "$O/.superseded-20261009"; chown ec2-user: "$O/.superseded-20261009"
    mv "$O/$n" "$O/.superseded-20261009/$n" && msg="moved" || msg="mv FAILED"
  else msg="NOT moved (running procs $run, dir $( [ -d "$O/$n" ] && echo yes || echo no))"; fi
  echo "p$k $n: last ledger [$last], pipeline starts so far $hold: $msg" | tee -a $R
done
for k in 1 2 3; do grep -e "retry" /data/logs/batch4p$k.log | tail -4 | cut -c1-140; done
