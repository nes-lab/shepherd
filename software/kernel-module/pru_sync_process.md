# SYNC_PROCESS between kernel-module & PRU

## Main Goal

- synchronize system time with pru
- adapting period length of loop (like PLL) via clock-skewing
- see python-simulation for details regarding PLL & PI-Tuning

## Mechanism High Level Init

- PRU1 signals ready-to-start with sync-reset-message (and waits in `event_loop()`, gpio-state = 1)
- kMod reacts by sending a TS for the next interrupt and starts the interrupt-trigger (in `trigger_loop_start()`)
- PRU1 sets TS on interrupt and starts main-loop (still in `event_loop()`, gpio-state = 2)

## Mechanism High level Runtime

- kernels `trigger_loop_callback()`
  - Kernel sends pseudo-interrupt to PRU1 for taking a counter-snapshot
  - both, kMod and PRU, take a timestamp
- PRU sends current period-counter1 (`Sync-Event 1`, gpio-state = 3) and switches to "reply pending"
- Kernel feeds the TS-difference into a PI-Controller and calculates a value for clock-correction
- PRU waits for response message to adjust clock-skew (in `Sync-Event 3`, gpio-state 2)
- PRU adjusts skew over one 100 ms window continuously, and readjusts every 10us, in `Sync-Event 2`, gpio-state = 1
- kernel readjusts control-loop-parameters as soon as timing-thresholds are crossed

## How to debug?

- Logic-Analyzer on:
  - P8_19 -> kernel states
  - P8_28, P8_30 -> PRU1 sync events described above
  - P8_12, P8_11 -> PRU0 sample-events
- `dmesg -wH` shows PI-errors and feedback-values for PRU

## What if it does not work?

The system is responsive, but delicate.
It needs a proper synced / stable environment and can only compensate for 1 % clock-skew of host-system.
A misbehaving `phc2sys` can skew a lot and the pru-sync can't keep up.
That error can be identified by looking at dmesg:

```Shell
[Apr11 17:15] shprd.sync: err_PI = -34096634 (22589131), -6546362 -> fback = -200000 ns/.1s [2020; 0]
[  +2.222228] shprd.sync: err_PI = 44103042 (30477031), -6030455 -> fback = 200000 ns/.1s [1980; 0]
[  +2.222221] shprd.sync: err_PI = 21625843 (29102235), -1118396 -> fback = 200000 ns/.1s [1980; 0]
[  +2.222228] shprd.sync: err_PI = -1019315 (20477815), -282776 -> fback = -200000 ns/.1s [2020; 0]
[  +2.222216] shprd.sync: err_PI = -23195183 (19711964), -3476991 -> fback = -200000 ns/.1s [2020; 0]
```

The last values in []-Brackets are the loop-correction and alternate between min and max (1980 & 2020 ticks per 10 us loop)

Phc2Sys shows indeed max clock-correction:

```Shell
 sudo systemctl status phc2sys@eth0
● phc2sys@eth0.service - Synchronize system clock or PTP hardware clock (PHC)
     Loaded: loaded (/etc/systemd/system/phc2sys@.service; enabled; preset: enabled)
     Active: active (running) since Fri 2025-04-11 16:31:19 CEST; 45min ago
       Docs: man:phc2sys
    Process: 367 ExecStartPre=/bin/sleep 5 (code=exited, status=0/SUCCESS)
   Main PID: 461 (phc2sys)
      Tasks: 1 (limit: 1025)
     Memory: 384.0K
        CPU: 938ms
     CGroup: /system.slice/system-phc2sys.slice/phc2sys@eth0.service
             └─461 /usr/sbin/phc2sys -r -w -s eth0 -E linreg

Apr 11 17:16:46 sheep0 phc2sys[461]: [2199.812] CLOCK_REALTIME phc offset 345801429016 s2 freq +100000000 delay   1725
Apr 11 17:16:47 sheep0 phc2sys[461]: [2200.812] CLOCK_REALTIME phc offset 345690277750 s2 freq +100000000 delay   1725
Apr 11 17:16:48 sheep0 phc2sys[461]: [2201.812] CLOCK_REALTIME phc offset 345579123936 s2 freq +100000000 delay   1725
Apr 11 17:16:49 sheep0 phc2sys[461]: [2202.813] CLOCK_REALTIME phc offset 345467970258 s2 freq +100000000 delay   1725
Apr 11 17:16:50 sheep0 phc2sys[461]: [2203.813] CLOCK_REALTIME phc offset 345356811688 s2 freq +100000000 delay   1725
Apr 11 17:16:51 sheep0 phc2sys[461]: [2204.814] CLOCK_REALTIME phc offset 345245656089 s2 freq +100000000 delay   1762
Apr 11 17:16:52 sheep0 phc2sys[461]: [2205.814] CLOCK_REALTIME phc offset 345134502717 s2 freq +100000000 delay   1725
Apr 11 17:16:53 sheep0 phc2sys[461]: [2206.814] CLOCK_REALTIME phc offset 345023349115 s2 freq +100000000 delay   1725
Apr 11 17:16:54 sheep0 phc2sys[461]: [2207.815] CLOCK_REALTIME phc offset 344912179492 s2 freq +100000000 delay   1725
Apr 11 17:16:55 sheep0 phc2sys[461]: [2208.815] CLOCK_REALTIME phc offset 344801025466 s2 freq +100000000 delay   1725
Apr 11 17:16:56 sheep0 phc2sys[461]: [2209.816] CLOCK_REALTIME phc offset 344689866486 s2 freq +100000000 delay   1725
```

To resync a ptp-environment a simply `shepherd-herd resync` helps. It will do:

```Shell
sudo systemctl stop phc2sys@eth0
sudo systemctl stop ptp4l@eth0
sudo ntpdate -s time.nist.gov
sudo systemctl start phc2sys@eth0
sudo systemctl start ptp4l@eth0
# restart kernel module
sudo shepherd-sheep fix
```

If there is no PTP running, simply disable `phc2sys` and `PTP` with

```shell
sudo systemctl stop ptp4l@eth0
sudo systemctl stop phc2sys@eth0
sudo shepherd-sheep fix
```

The kernel module is now able to sync the PRU

```Shell
dmesg -wH
[  +0.000946] shprd.sync: pru1-init with reset of time to 1744385823500000000 - starting loop
[  +0.000018] shprd.k: [test passed] received answer from pru0 / pipeline 1
[  +0.000014] shprd.k: [test passed] received answer from pru0 / pipeline 2
[  +0.019551] shprd.sync: NOTE - next message is shown every 2 s when sync-error exceeds 300 ns (normal during startup)
[  +0.000025] shprd.sync: err_PI = -60 (16000012), -5 -> fback = -71 ns/.1s [2000; 71]
[  +2.039581] shprd.sync: err_PI = 37113046 (37578062), 10000000 -> fback = 200000 ns/.1s [1980; 0]
[  +2.000015] shprd.sync: err_PI = 33305917 (34063907), 10000000 -> fback = 200000 ns/.1s [1980; 0]
[  +1.999977] shprd.sync: err_PI = 29498881 (30260229), 10000000 -> fback = 200000 ns/.1s [1980; 0]
[  +2.000003] shprd.sync: err_PI = 25691878 (26453213), 10000000 -> fback = 200000 ns/.1s [1980; 0]
[  +1.999998] shprd.sync: err_PI = 21884792 (22646200), 10000000 -> fback = 200000 ns/.1s [1980; 0]
[  +1.999993] shprd.sync: err_PI = 18077555 (18839015), 10000000 -> fback = 200000 ns/.1s [1980; 0]
[  +2.000006] shprd.sync: err_PI = 14270689 (15032132), 10000000 -> fback = 200000 ns/.1s [1980; 0]
[  +1.999995] shprd.sync: err_PI = 10463613 (11224986), 10000000 -> fback = 200000 ns/.1s [1980; 0]
[  +2.000018] shprd.sync: err_PI = 6656424 (7417912), 10000000 -> fback = 200000 ns/.1s [1980; 0]
[  +1.999986] shprd.sync: err_PI = 2849435 (3610844), 10000000 -> fback = 200000 ns/.1s [1980; 0]
[  +1.399985] shprd.sync: error BELOW 1ms -> relax PI-tuning
[  +0.600008] shprd.sync: err_PI = -957495 (692164), 9869916 -> fback = 200000 ns/.1s [1980; 0]
[  +0.999991] shprd.sync: error ABOVE 2ms -> more responsive PI-tuning
[  +1.000019] shprd.sync: err_PI = -4764767 (4008987), 5321593 -> fback = 75226 ns/.1s [1993; 5226]
[  +1.999993] shprd.sync: err_PI = -1597624 (2330823), -774841 -> fback = -200000 ns/.1s [2020; 0]
[  +0.799987] shprd.sync: error BELOW 1ms -> relax PI-tuning
[  +1.200009] shprd.sync: err_PI = 1543937 (1346758), -736406 -> fback = 113589 ns/.1s [1989; 3589]
[  +2.000010] shprd.sync: err_PI = 249223 (393382), -115061 -> fback = 22145 ns/.1s [1998; 2145]
[  +0.799985] shprd.sync: error BELOW 200us -> relax PI-tuning
[  +1.200007] shprd.sync: err_PI = 101486 (136653), -17580 -> fback = 10355 ns/.1s [1999; 355]
[  +2.000006] shprd.sync: err_PI = 6748 (26925), 4162 -> fback = 6019 ns/.1s [2000; 6019]
[  +1.999996] shprd.sync: err_PI = 9679 (8869), 8051 -> fback = 10715 ns/.1s [1999; 715]
[  +2.000003] shprd.sync: err_PI = 7201 (9596), 8633 -> fback = 10615 ns/.1s [1999; 615]
[  +2.000002] shprd.sync: err_PI = -16455 (10085), 7866 -> fback = 3337 ns/.1s [2000; 3337]
[  +1.999998] shprd.sync: err_PI = 19909 (10474), 8682 -> fback = 14162 ns/.1s [1999; 4162]
[  +2.000003] shprd.sync: err_PI = -18404 (11233), 8939 -> fback = 3873 ns/.1s [2000; 3873]
[  +1.999998] shprd.sync: err_PI = 6411 (9059), 8943 -> fback = 10707 ns/.1s [1999; 707]
[  +1.999992] shprd.sync: err_PI = -6550 (10251), 8645 -> fback = 6842 ns/.1s [2000; 6842]
```
