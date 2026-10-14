set +e
date -u +%T
cd /data/cregit-ec2
du -sh --apparent-size . 2>/dev/null; du -sh . ; find . -xdev | wc -l
for d in $(ls -A); do echo "$(du -s -BM "$d" 2>/dev/null | cut -f1) $d"; done | sort -rn | head -12
echo "build dir: $(ls tokenizeByBlobId/build 2>/dev/null | wc -l) entries"
ls -la .devenv 2>/dev/null | head; readlink -f .devenv/profile 2>/dev/null
echo "abs path refs (text files <1MB, excluding .git, build, target):"
grep -rIl --exclude-dir=.git --exclude-dir=build --exclude-dir=target --exclude-dir=.devenv -e /data/cregit-ec2 . 2>/dev/null | head -10
echo "symlinks pointing into /data/cregit-ec2:"; find . -xdev -type l -lname '/data/cregit-ec2*' 2>/dev/null | head
git status --short | head -5; git rev-parse HEAD
for k in 1 2 3; do echo "p$k running: $(grep '♥' /data/logs/batch4p$k.log | tail -1 | cut -c1-250)"; done
df -BG /b4p1 | tail -1
