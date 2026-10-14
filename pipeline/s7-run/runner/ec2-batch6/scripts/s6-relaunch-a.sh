X=a
set -uo pipefail
/usr/local/bin/census-fed-workload batch6 --commit 9ccead6716a619a7e3ddc7bad9234f14deae865c --bundle s3://${RUNNER_BUCKET}/cregit/cregit-9ccead6.bundle --bundle-sha256 64a4f3f081a91694b1976d531883c6ad547c54116a625d384c0d03785d935e06 --want-pq 40511e0de1a285b5bbc4ae0ff277e4775c5d67709966dd7c64dc9163c638fc5d
/usr/local/bin/census-fed-enqueue batch6 $X || exit 1
/usr/local/bin/census-fed-workload batch7 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
/usr/local/bin/census-fed-enqueue batch7 $X || exit 1
/usr/local/bin/census-fed-workload batch9 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
/usr/local/bin/census-fed-enqueue batch9 $X || exit 1
/usr/local/bin/census-fed-workload batch11 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
/usr/local/bin/census-fed-enqueue batch11 $X || exit 1
/usr/local/bin/census-fed-workload batch12 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
/usr/local/bin/census-fed-enqueue batch12 $X || exit 1
/usr/local/bin/census-fed-workload batch13 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
/usr/local/bin/census-fed-enqueue batch13 $X || exit 1
/usr/local/bin/census-fed-workload batch14 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
/usr/local/bin/census-fed-enqueue batch14 $X || exit 1
/usr/local/bin/census-fed-workload batch15 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
/usr/local/bin/census-fed-enqueue batch15 $X || exit 1
/usr/local/bin/census-fed-workload batch16 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
/usr/local/bin/census-fed-enqueue batch16 $X || exit 1
/usr/local/bin/census-fed-workload batch17 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
/usr/local/bin/census-fed-enqueue batch17 $X || exit 1
/usr/local/bin/census-fed-workload batch18 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
/usr/local/bin/census-fed-enqueue batch18 $X || exit 1
/usr/local/bin/census-fed-workload batch19 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
/usr/local/bin/census-fed-enqueue batch19 $X || exit 1
/usr/local/bin/census-fed-workload batch20 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
/usr/local/bin/census-fed-enqueue batch20 $X || exit 1
/usr/local/bin/census-fed-workload batch21 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
/usr/local/bin/census-fed-enqueue batch21 $X || exit 1
/usr/local/bin/census-fed-workload batch22 --commit 57551d7ad82a784615c1490623d72cb9dc994ba1 --bundle s3://${RUNNER_BUCKET}/cregit/cregit-57551d7.bundle --bundle-sha256 18b1bf1c87230460f59e433f0c5106f21dde77bfbc057a42776acb592a6eb71e --want-pq 14eb5d728ca6fa50623cb89088ab59348e646f1205ed3cf9f48bff0142eab799
/usr/local/bin/census-fed-enqueue batch22 $X || exit 1
sleep 70; echo "feeder: $(cat /run/census-fed-feeder.status)"
