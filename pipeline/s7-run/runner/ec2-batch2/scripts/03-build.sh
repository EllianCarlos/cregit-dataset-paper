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
