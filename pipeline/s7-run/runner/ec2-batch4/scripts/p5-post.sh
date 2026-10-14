set +e
systemctl daemon-reload
echo "after:  $(systemctl show census-batch2.service census-batch3L.service -p MainPID -p ActiveEnterTimestamp | tr '\n' ' ')"
[ "$(systemctl show census-batch2.service census-batch3L.service -p MainPID -p ActiveEnterTimestamp | tr '\n' ' ')" = "$PIDS_BEFORE" ] && echo "batch 2 / 3L main PIDs and start times unchanged by the daemon-reload"
systemctl show census-batch2.service census-batch3L.service -p OOMPolicy -p NeedDaemonReload | tr '\n' ' '; echo
systemctl show census-batch4p1.service census-batch4p2.service census-batch4p3.service -p OOMPolicy -p LoadState -p RequiresMountsFor | tr '\n' ' '; echo
D=$S3
echo "== T1 census-other-done batch4 (batch 2 running) -> 1"; $B/census-other-done batch4; echo "rc=$?"
echo "== T2 census-other-done batch2 (batch3L running) -> 1"; $B/census-other-done batch2; echo "rc=$?"
echo "== T3 census-other-done batch3L (batch 2 running) -> 1"; $B/census-other-done batch3L; echo "rc=$?"
echo "== T4 batch2: batch3L faked done (dryrun DONE, no units), batch 4 not started and no batch4/final/DONE -> 1"
DONE_URL_batch3L=$D/batch3L/dryrun/DONE UNITS_batch3L= $B/census-other-done batch2; echo "rc=$?"
echo "== T5 batch4: batch2 + batch3L faked done -> 0"
DONE_URL_batch2=$D/batch2/dryrun/DONE UNITS_batch2= DONE_URL_batch3L=$D/batch3L/dryrun/DONE UNITS_batch3L= $B/census-other-done batch4; echo "rc=$?"
echo "== T6 batch3L: batch2 faked done, batch4 faked done via batch2/dryrun/DONE and no units -> 0"
DONE_URL_batch2=$D/batch2/dryrun/DONE UNITS_batch2= DONE_URL_batch4=$D/batch2/dryrun/DONE UNITS_batch4= $B/census-other-done batch3L; echo "rc=$?"
echo "== T7 bad arg -> 2"; $B/census-other-done batchX 2>&1; echo "rc=$?"
echo "== T8 decide-only of the three finalizes (real state) -> no power-off"
$B/census-batch2-finalize --decide-only | tail -1
$B/census-batch3L-finalize --decide-only | tail -1
$B/census-batch4-finalize --decide-only | tail -1
echo "== T9 dry run of the batch 4 finalize: p1 = libexpat check output, p2/p3 = empty parts -> batch4/dryrun/, no power-off"
CTP_p1=/b4p1/ctp-check OUT_p1=/b4p1/libexpat-check/out MANIFEST=/home/ec2-user/batch2-input/manifest.libexpat.tsv \
  $B/census-batch4-finalize --dry-run | tail -4
echo "dry rc=${PIPESTATUS[0]}; objects in batch4/dryrun: $(aws s3 ls $D/batch4/dryrun/ --recursive | wc -l)"
echo "== T10 guard and live once"
$B/census-batch4-guard
sudo -u ec2-user $B/census-batch4-live; echo "live rc=$?"
aws s3 cp $D/batch4/live/progress.txt - | head -3
systemctl is-active census-batch2.service census-batch3L.service; uptime
