#!/bin/bash
# copy to /usr/local/bin/set-ptp-kworker-prio.sh (with chmod +x)
# Give the kernel PTP workqueue thread real-time priority
# Wait a tiny moment to ensure the kthread is fully spawned
sleep 0.2
#
# The kworker command line typically contains "ptp0", "ptp1", etc.
pgrep -f "ptp[0-3]" | while read pid; do
    sudo chrt -f --pid 60 "$pid"
done
# check with
pgrep -f "ptp[0-9]+" | xargs -I {} chrt -p {}
#
# TODO: test to bump ALL kworker
#pgrep -f "kworker" | while read pid; do
#    sudo chrt -f --pid 61 "$pid"
#done
# check with
pgrep -f "kworker" | xargs -I {} chrt -p {}
#
# TODO: test to bump network-services
#pgrep -f "network" | while read pid; do
#    sudo chrt -f --pid 61 "$pid"
#done
# check with
pgrep -f "network" | xargs -I {} chrt -p {}
