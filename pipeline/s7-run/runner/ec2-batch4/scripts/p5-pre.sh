set -euo pipefail
export AWS_PAGER=""
B=/usr/local/bin; S3=s3://${RUNNER_BUCKET}
echo "== pre-checks $(date -u +%FT%TZ)"
[ "$(sha256sum $B/census-batch2-finalize | cut -d' ' -f1)" = dbd1050b02367b1b45936e1f0ef1ba62cc5a55130f1033c2b2acdff4884e283d ] || { echo "census-batch2-finalize changed"; exit 1; }
[ "$(sha256sum $B/census-batch3L-finalize | cut -d' ' -f1)" = ec8b3b4d966cf3638be3d04e53e2e3e6b3bc425b3aa1e77a999ae0634b535d1e ] || { echo "census-batch3L-finalize changed"; exit 1; }
[ "$(sha256sum $B/census-other-done | cut -d' ' -f1)" = 36c27cd75bec632806bceac1991f49413276794c702c48904d7bfb6b6dce2ffa ] || { echo "census-other-done changed"; exit 1; }
echo "finalize scripts and census-other-done are the expected versions (sha256 dbd1050b.., ec8b3b4d.., 36c27cd7..)"
echo "callers of census-other-done: $(grep -l census-other-done $B/* /etc/systemd/system/* 2>/dev/null | grep -v -e census-other-done -e '\.orig' | tr '\n' ' ')"
[ -e $B/census-other-done.orig-2census ] || cp -p $B/census-other-done $B/census-other-done.orig-2census
for u in census-batch2.service census-batch3L.service census-batch3L-wait.service census-batch2-live.timer census-batch3L-live.timer census-batch2-finalize.service census-batch3L-finalize.service; do
  [ "$(systemctl show $u -p NeedDaemonReload --value)" = no ] || { echo "$u: NeedDaemonReload=yes, a daemon-reload would change it; aborting"; exit 1; }
done
echo "NeedDaemonReload=no for all batch 2 / batch 3L units"
PIDS_BEFORE="$(systemctl show census-batch2.service census-batch3L.service -p MainPID -p ActiveEnterTimestamp | tr '\n' ' ')"
echo "before: $PIDS_BEFORE"
for k in 1 2 3; do [ -e /b4p$k/ctp/STOP ] && { echo "STOP in /b4p$k/ctp"; exit 1; }; done
mkdir -p /data/logs
