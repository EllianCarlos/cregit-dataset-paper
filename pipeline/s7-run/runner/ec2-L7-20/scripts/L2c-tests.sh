# L2c-tests.sh: the power-off rule tests T2-T5 and waiter W5 again (the env/function mix of L2b broke them).
set -uo pipefail
export AWS_PAGER=""
B=/usr/local/bin; F=s3://${RUNNER_BUCKET}/batch4/dryrun/DONE
t() { local d=$1; shift; out=$( ( export "$@"; $B/census-other-done $SELF ) 2>&1); echo "$d: rc=$? $out" | cut -c1-200; }
base="DONE_URL_batch2=$F UNITS_batch2= DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch4=$F UNITS_batch4= DONE_URL_batch5L=$F UNITS_batch5L="
SELF=batch6L t "T2 batch6L, 2+3L+4+5L faked (L7-20 missing)" $base
SELF=batch6L t "T3 batch6L, 2+3L+4+5L+L7-20 faked" $base DONE_URL_L7_20=$F UNITS_L7_20=
SELF=L7-20 t "T4 L7-20, 2+3L+4+5L+6L faked" $base DONE_URL_batch6L=$F UNITS_batch6L=
SELF=batch6L t "T5 batch6L, all faked, L7-20 waiter active (real unit list)" $base DONE_URL_L7_20=$F
SELF=batch2 t "T5b batch2, 3L+4+5L+6L+L7-20 faked" DONE_URL_batch3L=$F UNITS_batch3L= DONE_URL_batch4=$F UNITS_batch4= DONE_URL_batch5L=$F UNITS_batch5L= DONE_URL_batch6L=$F UNITS_batch6L= DONE_URL_L7_20=$F UNITS_L7_20=
w() { local d=$1; shift; out=$( ( export COUNTS_batch2='1 0' COUNTS_batch3L='1 0' COUNTS_batch4p1='1 0' COUNTS_batch4p2='1 0' COUNTS_batch4p3='1 0' COUNTS_batch5L='2 0' COUNTS_batch6L='3 0' MEMAVAIL_GB=200 DATAFREE_GB=3000 B6L_STARTED=1 INPUT_OK=1 GATE_OK=1 ACTIVE_batch2=active ACTIVE_batch3L=active ACTIVE_batch4p1=active ACTIVE_batch4p2=active ACTIVE_batch4p3=active ACTIVE_batch5L=active ACTIVE_batch6L=active; export "$@"; $B/census-L7-20-wait --decide-only ) 2>&1); echo "$d: rc=$? ${out:0:60} ... ${out: -60}"; }
w "W2 10 other running, all met"
w "W5 11 other running" COUNTS_batch6L='4 0'
