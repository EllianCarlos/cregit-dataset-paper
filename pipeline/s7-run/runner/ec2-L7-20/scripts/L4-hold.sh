# hold the L7-20 waiter while its inputs are replaced by v2 (batch21L added): STOP in /bL7/ctp plus a marker
set -u
[ -e /bL7/ctp/STOP ] && echo "STOP already there: $(ls -la /bL7/ctp/STOP*)"
touch /bL7/ctp/STOP; chown ec2-user: /bL7/ctp/STOP
echo "held $(date -u +%FT%TZ) for the L7-20 v2 inputs (batch21L added); removed by census-L7-20-v2swap" > /bL7/ctp/STOP.v2-hold
echo "census-L7-20: $(systemctl is-active census-L7-20.service); waiter: $(systemctl is-active census-L7-20-wait.service)"
sleep 65; cut -c1-300 /run/census-L7-20-wait.status
ls -la /home/ec2-user/L7-20-input/ | tail -4
