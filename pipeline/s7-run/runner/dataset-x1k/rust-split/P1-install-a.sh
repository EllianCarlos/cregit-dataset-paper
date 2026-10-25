#!/usr/bin/env bash
# P1-install-a.sh, machine A (root, through scripts/a/ssm-a.sh; after E1; made by render.sh from
# src/P1-install-a.body; idempotent). Installs the pull of the aws-sdk-rust split:
#   /usr/local/lib/rust-split/rs_pull.py, /usr/local/bin/rs-pull, /etc/rust-split/pull.env,
#   rs-pull.service (oneshot, root) and rs-pull.timer (OnBootSec=5min, OnUnitActiveSec=10min).
# R8 (x1k-rebalance.timer) also runs every 10 min. They do not conflict: R8 only reads .blame
# counts and mtimes; the pulled files keep the mtime of the extra (the time it finished them),
# so R8's rate of the row counts them as the row's output, which is what the row's end time needs.
# A restart of the row by rs-pull takes R8's lock (rebalance.lock), so the two never restart at once.
# Then it runs rs-pull once and prints its log block.
# Env: AUTO_RESTART (1), STALE_MIN (40), RESTART_MIN (100).
set -uo pipefail
IID=$(cat /sys/devices/virtual/dmi/id/board_asset_tag)
[ "$IID" = ${RUNNER_EC2_X1K_LONG_A4} ] || { echo "ABORT: $IID is not machine A"; exit 1; }
S=/data/x1k-long/rust-split
LIB=/usr/local/lib/rust-split
AUTO_RESTART=${AUTO_RESTART:-1}; STALE_MIN=${STALE_MIN:-40}; RESTART_MIN=${RESTART_MIN:-100}
echo "== $(date -u +%FT%TZ) P1 install on $IID"
[ -s $S/e1/left.tsv ] && [ -s $S/e1/settings.env ] && [ -d $S/e1/parts ] || { echo "ABORT: run E1 first"; exit 1; }
N=$(sed -n 's/^N=//p' $S/e1/settings.env)
case $N in ''|*[!0-9]*) echo "ABORT: no N in e1/settings.env"; exit 1 ;; esac
mkdir -p $LIB /etc/rust-split $S/state
chown ec2-user: $S $S/state
# embedded lib/rs_pull.py (sha256 fced9a9ec42d4b84)
mkdir -p "$(dirname "$LIB/rs_pull.py")"
base64 -d <<'EOF_RS_EMBED' | gunzip > "$LIB/rs_pull.py.tmp"
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
LgAA
EOF_RS_EMBED
[ "$(sha256sum < "$LIB/rs_pull.py.tmp" | cut -d" " -f1)" = fced9a9ec42d4b840e7111e1411451b3b2b0281db21069e5a5b16f39a93cf0c2 ] || { echo "ABORT: embedded lib/rs_pull.py sha256"; exit 1; }
chmod 755 "$LIB/rs_pull.py.tmp" && mv -f "$LIB/rs_pull.py.tmp" "$LIB/rs_pull.py"
# embedded lib/rs-pull.sh (sha256 4bc604850d4a25b7)
mkdir -p "$(dirname "/usr/local/bin/rs-pull")"
base64 -d <<'EOF_RS_EMBED' | gunzip > "/usr/local/bin/rs-pull.tmp"
H4sIAAAAAAAC/5VZf3faxhL9n08xUWmBBCFwkiaG4lM7cV794hqOwad9afJ8BCxGz0KiWmHsOv7u
787sSghw0jTHJwhpNTs/7szcWb574i114o2CyFPRDY18PSt9R4l2F8swpOrcH8+CSNFhnZI4TjvZ
k0YazFVC6kYld9Rq0jyI6hREOvXDUE1odEf9lmu/u35Dz2oNiB3OFInceEoprv2VdvXk2k2WOiW9
CIO0jVVErYYsa8uiSK1oHM8XoUoV9EvHM6VZgH7e9rwjb+Knvlape9u69liOK3K8eJl6P10fePYF
D8qlMcuTDfBvFPpzRZMgyZRJ4lWdVkE6g42XYuPijnxNarznLjWMreqZv/fyxzrN1XykEl2nhZ+k
FEGO7lAYRNfVvRo9yzZYRnyrDf3hJPIjivG5SoJUdcinVM0XZvdIdp8GoSJ9p3E/UyjXsNYRmXsN
uQ2fpkvdSG9TXqgQIKNHFfbxM+WZFV6dpnFC/T37+vMGHVY0u1Oxt1O8g0gF0UTdUrVo8iLWNXIP
qODNcRylSRx6vouHvLUJjbpNE19nBotIimJjiw/1EhqpMF5RkNIiXGp+BxbP/eQqiIxSL4xNKpq0
aTVTkUWUGBRoSIoCPYOafjRhyRJNWvlBCu/zPbYoDGDPLA4nWnbmbfw0U2qlEoM5FjJNEQl5xc9c
QFXIMiJWCPZoGYQp684y7AreB7pEcUqA0vhaTTLh/pUfRDWkhjIrLYwQ07EyUOI7569pkcRjNVlC
lepZ73Lwy8Xwbe+3szo2iBd1s009C26S6x5y5s05N2b+jSJnmsRzFwhZ0Ku6I2o5ghH3f/FI00//
7h0NDupOrSF5xmkjZunrYKGtXxuyvpFt0IvCO6Pn4cWwd3l+PBgeng+7rTrAO4GrWKMwHl8z0GBF
NVEjP/RhXIPv1kwIDL5XMwk6XS39JPePAEHdQgsN8EV3pJIEoJAk0EV8HZ4enw+RQz4HKFlGAhVk
DOsnuLTFo98Sl7XtdpL8HjLfDePoqpj+v/RO39qdGX2TWEkAUcuujHsGz0U7yM2wPRj2+oK5OCmA
G2k1U3cM0FrHbB+gfrFOGkoIUPBY47nxhkUzjLDClxFU8Iml94/fGmT7a2SzZccovFUOLnkqHRfN
ENtRl2ttAlqKQapDIrx2+esJHth7/KVD73rnb47XsaRq/3kNmxgYCEKhGoCeCqL5hsQMERoqSaT4
WrfpfHA5hIg6X5yeHMnn0cWb98d8q9cb1iHy99b7y8PBgG/x5S+9X4/N1fkFlBr8ZzA8/vXN8BQv
XJwdDurU753iC9YPT4/Z7t4yXSxRSqyTONqcBUm8vJrBpfAowox8nyQxI5grHSdlcBU16DS+atty
J04K46tGCX2A3GVMi2Chpn4QlvpdtJjQH+nLy2KvKbEF3fI9f7TdTRQ9lAbdMj8oxKF0xIszB7Rd
aT3jRF0FqTtWkV5qd7/58kXrdfPF8/39V2gXq72HUv/d793Hu1NJvAaZuQehBYq/N1E3wRjd6iZI
0qUfepN54AUTbxQjQJe+hqTL1IeK7OoL+z5f4/VZPFde1qseSnD5W7sAl3iOrIJpWUzwKL+GPdJ3
xmn4gKhIsDgRRFXTN1cxAMKtarFM0AFQxnzuyXNG/CJR0+AW/V1eZEfxJ/wcSdd0l+sO6rrwCkCA
RfzRdl8+dCweWCG5aLt7zYfSH+ROv5gN9Il++IGw5C9yJC6M1Lb74JgHjS++WDrDNmdm242KV74v
fm27LdYryy9WLbtuuy+aeFZIODZ4/Q2vNqE+MsYgBhfwPTMsVEwENAxGBcUeSlxsbuBjOttQaL15
cStJIOuvDmpaiWgMdFH5/snNAwupVD4//eNJ093/9LQGr89icg6PejCIyjddu8o0Mh+pFaMMREum
Mk6Ha2VKLergSvvj0iSOVOnkBBCqjpFzTllQ6tDeAWPUi+DQGoLklLHGoS4FbrP5cr85GbXUq/He
j/uT5gsE4/Nnut/S4x4vtF208mCSK5OTzFyPDj2U5tdMj9wFNhl4RWLjlNStGtP+wcH6ia0B42uH
NzVCSlPpXW5E+0VNul0qV5GXiqH57Pt3w++HH2oZr22jiKNNmC5kSUXWBR06OKCdLa8ypZusdGkO
RlCt0T1iIxGnIR0hZkM6hakrIVco/8IWJsR9Gwu/QS/OPfY1+kC3fLYF3seR0y0/CiIUt/UXB7sH
U04lJZZx20QWdUz7NXoRFZppO+uixAiB6YlKl0nExk8DCIM2YAn+hKkvp7BjSmm576B9HiHxh8LM
y31PmAhnGd9bpwT4jX+lIAk6gd+Uj06dTSCR8MCMGn9FnwcjZCqGqZYXqmnaSPWNk5ePSfaIm7Le
2cdCFtsdt4RKac4xeWO9UctsVDZVs4jZoUAxW4Y1sD7DDktjKgImbSLwJJPA5W34oXsxfMPTEYYc
AtFw3USNl4kOmAWWj+C+d7+LHwFJ3DhtpPMF52YBndkOYFyOCWeJGRms1l9YZdyyY77RgLupmuyY
LTGf3xgvWzVw4eSgJrJbIPWrqzG5If0kK2p0re40L/wuG/fWblzcpbM4ek7uCa89OfLW44ljBkjX
tXJFGL6aLoRva9e46NO5u+QrQ8uG5qO4w3UNkgzOIIWBsIUKFwXEKZ9ZAanaKgGIMnMVqmjvvx6R
VxHYoS/1T/qcaMOLwR/NTw9cJJsGYZlnfjs8Pzs5+xdKTj7XYADxJzw3zfABi5YsWQZMTJ9KFQiP
5y+QLuCPQHTNuBHzoSmQdgyyY6SYwbGC2GtBMET9iVrPRtVsHxEQXiUYLdw/oVvuxfK1t543P5ZN
dAt4ogyl48UmMjdedHZqOJ7zA4MY12Xq5+pZvHJlQtA2PPwPmMwA9hURX3jolMwYgg/paOwmOwej
EAdpELMZXJRRt74FfFK/AT7Ukt26gvsxAzKvccxDeYiTNvEl/NTyNi7CH2/jeTrKmoosrRTSMW/c
XB5XXdtInn2va3kqGvFlPDZVI1Min+mddQIWg7q7bh3pnXOBrwQTgcxskeVtazDQGKU15/HM4IW0
XIQx8sHWIAni+tyA4yf9FEYbAPtU6aKZNp5Sxun5WtZUJDqIhmY+bMJSoDRI5RSbkNuySY3U57xm
cR+rfyAiww9t99PTjzVI9D6iRFRqxf1N9+a2cm/ugQ7uv2q6zRb+hs1mW/4+oBggMpsbW+ObLG/y
jWCcqHEwUd9YC/+miGUJ57oSFIMWXu67hq3gjlyILDAZxyBJ5IXKnQeRVFbLOBzpWfKCfVRkHbVC
fzBGAAyTnIzAfRtDbNttSv1s7TCTR2bdfFs5dWznZzM8rMtJRT4Ca980IBVqJdabLOQzsYwwIf+Q
WPg/oxWFPMuVLdIvh548pucGX2sKp8j0qjLRBH0c3aHo8zHYtgm7JEv+K9I2OT7Z5W3ZkwJ3y7fF
xA2g+7RQiQa3lIMtPirZ3c2+cZlI0IdOCSwXEU9SprlrC3kjRPEp02FTb75MZteLM0ptLGBSIZtp
kW0IdNShqJDb7ngnvTmrW5uzSa7EfSToEW5uzpA2juO4KaIxFA5/5RSOOYE5FZFDHWb/jVLBEZsM
v1tuUf8UFUYIPffubpOiJumQpjRFT+f3uw5jrV+kwMX2YBv0lCRZZL73zhgzR4enh2dvjp2Nu4M1
3hyuFG89ewyhF3HqYmRH5V0uUlTL7Dn76tGHctKRn+tlcbCkwCJsasmhNaQsnx0qTy2ynHV/nUon
zc8WMOK5/jhl4ppFy50GkR8Gf6mGVgkfd2wOlVkaTqUVmnc/y4fPNe7zRBW+JIo7A65q27qZM3Wz
EcAeyHEyhDqFDDYpxP4emfluO4HW+VK+lyUPu+khs+hrnkW3XJlPo+skGfsRz7vxAntsLdxh1tns
+npTBNBrptLN9815fF7r+IA8P8iM1G3K4+zOdPRomJj/ZaH6GXPb5vYsL/OmnCPIS8XKsrOLLnZm
95gq/yUa8CE299NPz4izt3/qbPRef3VNlftFArBSee9BuiyXWp1yH3i1PanZn4nM7xqQPFMCCgn5
vU75vCFSD3XR+NVXleUE7jJBzns/n6p3PXR6oQ7MGjCiFbRdI1aSf5u+SaUkh6WAtvGSCq+xctbH
MflBzCOMzmZhnv7Z7wc2K7ne8HyZxksMEY+t6+SeKtwlPi2tIpSSw/yjnQJiuBNDYK04wmWwwkBR
7lNVbBFTOvYHBYwUyLVJkfrKfbAAHl6o8tSsq8BtMgTWanySW+wQQ9mxgEg+599Eoi2Rl8UZ5nlT
Jphvh/IoUT7Kgw6VYnLLJ2pS7qR4oSB8kyBbJmxs4RPzq4BdbX5mMr/mxIuNzJaKETUZYakdNbfo
aG3TC3C9Sl3DfLeMKVTNzqbjhK79nef2XhjPcVp9WRtE8IpNjJpZC/ia/3T4FRL+GPfeyKIMbsYA
box8aGD7uJZBe7xMQQBa7usmGHijsf3YbB1TRX7fy340nkhRaDyt1AoM8x+Y/MgWf27/GPfFZYUf
6CRl6sXpOfOiOdJ1MlL5DzBoWXvmut77tinP5qWvcjGb1L33W+ea9oEWb4h8JsgZ2B9vAGRNIL2B
/o0Km8G/KA2VmH+nXEfccLBK0bkVoWCVHUdWdkVLbLl8mcMWm6bJ3BwffGtdTNQ8vpHDLst/TYMo
2dNdJN4P+Xy45B7xs+ddcWlLlWLgP3JEXJIT4t1DodL/AX1lMXJ/IQAA
EOF_RS_EMBED
[ "$(sha256sum < "/usr/local/bin/rs-pull.tmp" | cut -d" " -f1)" = 4bc604850d4a25b70975ca7d7d8cf681009daa16f9d6e0163d7b68e087245321 ] || { echo "ABORT: embedded lib/rs-pull.sh sha256"; exit 1; }
chmod 755 "/usr/local/bin/rs-pull.tmp" && mv -f "/usr/local/bin/rs-pull.tmp" "/usr/local/bin/rs-pull"
mkdir -p $S/state/pull $S/state/status; chown -R ec2-user: $S/state/pull
printf 'N=%s\nAUTO_RESTART=%s\nSTALE_MIN=%s\nRESTART_MIN=%s\n' "$N" "$AUTO_RESTART" "$STALE_MIN" "$RESTART_MIN" > /etc/rust-split/pull.env
cat > /etc/systemd/system/rs-pull.service <<'EOF_s'
[Unit]
Description=rust-split pull of aws-sdk-rust .blame batches from the extra machines
Wants=network-online.target
After=network-online.target
RequiresMountsFor=/data1 /data2
[Service]
Type=oneshot
ExecStart=/usr/local/bin/rs-pull
TimeoutStartSec=3000
EOF_s
cat > /etc/systemd/system/rs-pull.timer <<'EOF_t'
[Unit]
Description=rust-split pull every 10 min
[Timer]
OnBootSec=5min
OnUnitActiveSec=10min
[Install]
WantedBy=timers.target
EOF_t
systemctl daemon-reload
systemctl enable --now rs-pull.timer >/dev/null 2>&1
systemctl start rs-pull.service
echo "pull.env: $(tr '\n' ' ' < /etc/rust-split/pull.env)"
echo "timer: $(systemctl is-active rs-pull.timer); next: $(systemctl list-timers rs-pull.timer --no-legend --no-pager | awk '{print $1, $2, $3}')"
n=$(grep -n '^== .* rs-pull on' $S/state/pull.log | tail -1 | cut -d: -f1)
[ -n "$n" ] && tail -n +"$n" $S/state/pull.log | head -30 | sed 's/@//g'
echo "P1 install done $(date -u +%FT%TZ)"
