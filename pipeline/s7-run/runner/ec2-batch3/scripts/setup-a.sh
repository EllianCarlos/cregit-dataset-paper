X=a
set -euxo pipefail
uname -r; cat /etc/os-release | grep PRETTY
lsblk -d -o NAME,SIZE,MODEL
DEVS=$(lsblk -d -n -o NAME,MODEL | awk '/Instance Storage/{print "/dev/"$1}' | sort)
echo "instance store: $DEVS"; [ $(echo $DEVS | wc -w) -eq 4 ]
for i in $(seq 1 40); do dnf -y -q install mdadm git tmux python3.12 python3.12-pip xfsprogs nvme-cli tar xz && break; echo "dnf busy, retry $i"; sleep 15; done; command -v mdadm
if ! [ -e /dev/md0 ]; then mdadm --create /dev/md0 --level=0 --raid-devices=4 --run $DEVS; fi
mkfs.xfs -f /dev/md0 >/dev/null
mkdir -p /data; mount -o noatime /dev/md0 /data
df -h /data; cat /proc/mdstat
mkdir -p /data/input /data/logs
aws s3 cp s3://${RUNNER_BUCKET}/batch2/input/ /data/input/ --recursive --only-show-errors
cd /data/input && sha256sum -c SHA256SUMS
chown -R ec2-user:ec2-user /data
git --version; mdadm --version 2>&1; tmux -V; python3.12 --version; aws --version
nproc; free -g | head -2
# batch 3 spot: the batch 2 code inputs (bundles, libexpat check manifest) and the batch 3 manifests.
mkdir -p /data/input3
aws s3 cp s3://${RUNNER_BUCKET}/batch3/input/ /data/input3/ --recursive --only-show-errors
(cd /data/input3 && sha256sum -c SHA256SUMS)
mkdir -p /etc/cregit-census && echo "BATCH=$X" > /etc/cregit-census/batch.env
chown -R ec2-user:ec2-user /data
set -euxo pipefail
# keep the md array and mount across a reboot (not a stop)
mdadm --detail --scan > /etc/mdadm.conf
grep -q ' /data ' /etc/fstab || echo '/dev/md0 /data xfs noatime,nofail 0 0' >> /etc/fstab
if ! [ -d /nix/store ]; then
  sudo -u ec2-user -i bash -c 'curl -fsSL https://releases.nixos.org/nix/nix-2.34.6/install -o /tmp/nix-install && sh /tmp/nix-install --daemon --yes' > /data/logs/nix-install.log 2>&1 || { tail -40 /data/logs/nix-install.log; exit 1; }
fi
tail -5 /data/logs/nix-install.log
cat >> /etc/nix/nix.conf <<'C'
experimental-features = nix-command flakes
trusted-users = root ec2-user
max-jobs = auto
C
systemctl restart nix-daemon
sudo -u ec2-user -i bash -c '. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh; nix --version; nix profile add nixpkgs#devenv 2>&1 | tail -3 || nix profile install nixpkgs#devenv; command -v devenv; ls -la ~/.nix-profile/bin/devenv; devenv version'
sudo -u ec2-user -i bash -c 'set -e; git clone -q /data/input/cregit-ec2.bundle /data/cregit-ec2 -b ec2/census-batch2; git -C /data/cregit-ec2 log --oneline -1; git clone -q /data/input/ctp.bundle ~/ctp -b feat/e2e-runner; git -C ~/ctp log --oneline -1; git clone -q /data/input/ctp.bundle ~/ctp-check -b feat/e2e-runner; git -C ~/ctp-check log --oneline -1'
set -euo pipefail
cat > /home/ec2-user/build.sh <<'U'
set -euo pipefail
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cd /data/cregit-ec2
devenv shell -- bash -c 'set -e
echo SRCML_PREFIX=$SRCML_PREFIX; sha256sum $SRCML_PREFIX/lib/libsrcml.so.1.1.0
./run_pipeline_process.sh --build-only > /data/logs/build.log 2>&1 || { tail -40 /data/logs/build.log; exit 1; }
tail -2 /data/logs/build.log
make -C tokenize/srcMLtoken
ldd tokenize/srcMLtoken/srcml2token | grep -i srcml
ls -la blobExec/target/scala-2.13/*.jar slickGitLog/target/scala-2.10/*one-jar.jar persons/target/scala-2.10/*one-jar.jar remapCommits/target/scala-2.10/*one-jar.jar tokenize/rustTokenizer/target/release/rust_tokenizer'
for d in ~/ctp ~/ctp-check; do cd $d; python3.12 -m venv .venv; .venv/bin/pip install -q duckdb==1.5.5 pytest==9.1.1 coverage==7.16.0; done
cd ~/ctp; .venv/bin/python -c "import duckdb,sys;print(sys.version.split()[0], duckdb.__version__)"
.venv/bin/python -m pytest -p no:cacheprovider -o addopts= -q 2>&1 | tail -1
U
chown ec2-user: /home/ec2-user/build.sh
sudo -u ec2-user -i bash /home/ec2-user/build.sh
set +e
set -uo pipefail
mkdir -p /home/ec2-user/batch2-input && cp -p /data/input/* /home/ec2-user/batch2-input/ && chown -R ec2-user: /home/ec2-user/batch2-input
cat > /home/ec2-user/ctp-check.cfg <<'C'
# EC2 half of the machine-independence check (cregit 95cdc88); own ctp clone and output.
[paths]
cregit_dir = /data/cregit-ec2
output_dir = /data/ec2-check/out
C
cat > /home/ec2-user/check.sh <<'U'
set -uo pipefail
cd ~/ctp-check
export CTP_CONFIG=/home/ec2-user/ctp-check.cfg
I=/home/ec2-user/batch2-input
.venv/bin/python ctp.py census --manifest $I/manifest.libexpat.tsv --project-meta $I/project_meta.batch1.json \
  --workers 1 --retries 0 --skip-html --tokenizer-worker --blame-jobs 2 --memory-limit 2GB --min-free-mem-gb 10 > /data/logs/check.log 2>&1
echo "census rc=$?"; tail -3 /data/logs/check.log
echo "cregit HEAD $(git -C /data/cregit-ec2 rev-parse HEAD)"
sha256sum /data/ec2-check/out/libexpat__libexpat/libexpat__libexpat-dataset.parquet
ls -la /data/ec2-check/out/libexpat__libexpat/
U
chown ec2-user: /home/ec2-user/check.sh /home/ec2-user/ctp-check.cfg
sudo -u ec2-user -i bash /home/ec2-user/check.sh
echo "=== libexpat parquet sha256 expected 40511e0de1a285b5bbc4ae0ff277e4775c5d67709966dd7c64dc9163c638fc5d"
