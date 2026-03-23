# Testing Routine for new Capes

## Setup

What you need:

- a power source
- a beaglebone connected to your host system
- at least one shepherd cape
- target boards in each target port (one is enough, two is faster)

To prepare the beaglebone update this directory remotely (if not already done)

```Shell
cd /opt/shepherd/
git pull
```

## Routine

- connect new cape to Beaglebone & add targets
- power system up
- run the commands below
- copy data to host and run analys

On Beaglebone:

```shell
cd /opt/shepherd/hardware/tests_manual/
# TP 1
sudo shepherd-sheep program -pA -m1 -tnrf52 ./nrf52_testable.hex
sudo shepherd-sheep program -pA -m2 -tmsp430 ./msp430_testable.hex
sudo shepherd-sheep run ./config_emu_tp1_3V.yaml
sudo shepherd-sheep run ./config_emu_tp1_hrv.yaml
# TP 2
sudo shepherd-sheep program -pB -m1 -tnrf52 ./nrf52_testable.hex
sudo shepherd-sheep program -pB -m2 -tmsp430 ./msp430_testable.hex
sudo shepherd-sheep run ./config_emu_tp2_3V.yaml
sudo shepherd-sheep run ./config_emu_tp2_hrv.yaml
```

On Host:

```Shell
scp jane@sheep0://var/shepherd/recordings/emu_tp* ./
python3 emu_plot.py
```

## Analysis

- first look through the log to check if both MCUs on both target ports programmed successfully
- check power plot for an actual working analog frontend (varying current-draw)
- check the gpio-traces of the generated images. each GPIO should toggle individually - also both power good pins during `hrv` emulation

## Final Steps

Run the calibration with the SMU
