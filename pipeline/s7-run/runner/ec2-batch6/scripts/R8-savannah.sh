set -uo pipefail
for u in https://git.savannah.gnu.org/git/a2ps.git git://git.savannah.gnu.org/a2ps.git; do r=$(sudo -u ec2-user timeout 40 git ls-remote $u HEAD 2>&1 | head -1 | cut -c1-120); echo "$u -> rc=${PIPESTATUS[0]} $r"; done
