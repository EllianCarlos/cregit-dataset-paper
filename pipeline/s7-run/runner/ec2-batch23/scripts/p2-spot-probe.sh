# p2-spot-probe.sh (read-only): the lock use of census-fed-workload and census-fed-enqueue.
grep -n 'flock\|lock' /usr/local/bin/census-fed-workload /usr/local/bin/census-fed-enqueue /usr/local/bin/census-fed-common | cut -c1-200
