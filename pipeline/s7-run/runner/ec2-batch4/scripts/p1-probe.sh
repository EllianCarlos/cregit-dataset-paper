set +e
export AWS_PAGER=""
date -u +%FT%TZ; uptime
for u in census-batch2.service census-batch3L.service census-batch3L-wait.service census-batch2-live.timer census-batch3L-live.timer census-batch2-finalize.service census-batch3L-finalize.service; do
  echo "$u $(systemctl is-active $u) $(systemctl show $u -p NeedDaemonReload -p OOMPolicy -p FragmentPath -p DropInPaths | tr '\n' ' ')"; done
systemctl list-units 'census*' --all --no-pager --no-legend | awk '{print $1,$3,$4}'
df -BG /data / | cat
awk '/MemAvailable|MemTotal/' /proc/meminfo
echo "loop:"; losetup -a; lsmod | grep -c loop; ls /dev/loop* 2>/dev/null | head -3
cat /etc/fstab
findmnt -no SOURCE,FSTYPE,OPTIONS /data
echo "du llvm in batch3L:"; ls /data/census-2026-10-batch3L/ 2>/dev/null
for d in /data/census-2026-10-batch3L/*/; do echo "$(du -sBG "$d" 2>/dev/null | cut -f1) $d"; done
ls /home/ec2-user/ctp-b3L/state/ 2>/dev/null
for d in /home/ec2-user/ctp-b3L/state/*/ /home/ec2-user/ctp-b3L/work* ; do [ -e "$d" ] && echo "$(du -sBG "$d" 2>/dev/null | cut -f1) $d"; done
grep -n -i -e disk_floor -e "disk-floor" -e work_dir -e clone_dir /home/ec2-user/ctp-b3L/ctp.py | head -20
cat /home/ec2-user/census-batch3L.cfg
ls /home/ec2-user/ /home/ec2-user/batch2-input/
ls /usr/local/bin/ | grep census
sha256sum /usr/local/bin/census-batch2-finalize /usr/local/bin/census-batch3L-finalize /usr/local/bin/census-other-done
which mkfs.xfs xfs_info
