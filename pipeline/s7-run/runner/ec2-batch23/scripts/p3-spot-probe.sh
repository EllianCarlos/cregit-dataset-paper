# p3-spot-probe.sh (read-only): where the fed tools use the half or the part name.
cd /usr/local/bin
ls census-fed-* census-spot-decide 2>/dev/null | tr '\n' ' '; echo
grep -n 'half\|\$X\|\${p\|:0:1\|\[ab\]' census-fed-* census-spot-decide 2>/dev/null | grep -v '^census-fed-workload' | cut -c1-220
