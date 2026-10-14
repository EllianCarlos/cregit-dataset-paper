set -uo pipefail
cat > /home/ec2-user/bc.sh <<'U'
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cd /data/cregit-ec2
tail -3 /data/logs/build.log
devenv shell -- bash -c 'echo SRCML_PREFIX=$SRCML_PREFIX; sha256sum $SRCML_PREFIX/lib/libsrcml.so.1.1.0; srcml --version | head -1; ldd tokenize/srcMLtoken/srcml2token | grep -i srcml; ls -la blobExec/target/scala-2.13/*.jar slickGitLog/target/scala-2.10/*one-jar.jar persons/target/scala-2.10/*one-jar.jar remapCommits/target/scala-2.10/*one-jar.jar tokenize/rustTokenizer/target/release/rust_tokenizer tokenize/srcMLtoken/srcml2token' 2>&1 | grep -v -e Downloading -e '^•' -e '^✓'
cd ~/ctp; .venv/bin/python -c "import duckdb,sys;print(sys.version.split()[0], duckdb.__version__)"; .venv/bin/python -m pytest -p no:cacheprovider -o addopts= -q 2>&1 | tail -1
U
sudo -u ec2-user -i bash /home/ec2-user/bc.sh
