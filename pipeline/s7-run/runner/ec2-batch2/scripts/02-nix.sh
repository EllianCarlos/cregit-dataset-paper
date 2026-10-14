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
