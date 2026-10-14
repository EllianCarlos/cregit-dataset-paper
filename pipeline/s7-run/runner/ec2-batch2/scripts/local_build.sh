#!/usr/bin/env bash
# Build the cregit-ec2 artifacts locally, at nice 19, only while MemAvailable > 10 GB.
set -euo pipefail
memwait() { while [ "$(awk '/MemAvailable/{print int($2/1048576)}' /proc/meminfo)" -lt 10 ]; do echo "$(date -u +%T) MemAvailable < 10 GB, waiting"; sleep 60; done; }
. /nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh
cd ${RUNNER_HOME_LOCAL}/Projects/cregit-ec2
memwait
nice -n 19 ~/.nix-profile/bin/devenv shell -- bash -c 'set -e; echo SRCML_PREFIX=$SRCML_PREFIX; sha256sum $SRCML_PREFIX/lib/libsrcml.so.1.1.0; srcml --version | head -2; ./run_pipeline_process.sh --build-only; make -C tokenize/srcMLtoken; ldd tokenize/srcMLtoken/srcml2token | grep -i srcml'
echo BUILD_DONE rc=$?
