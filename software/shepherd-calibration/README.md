# shepherd-cal

*shepherd-cal* is the command line utility for calibrating and profiling a shepherd cape.

---

**Documentation**: [https://orgua.github.io/shepherd/](https://orgua.github.io/shepherd/)

**Source Code**: [https://github.com/orgua/shepherd](https://github.com/orgua/shepherd)

---

## Installation

*shepherd-cal* is a pure python package and currently NOT available on PyPI.
For install from local sources:

```Shell
cd shepherd/software/shepherd-calibration/
pip3 install ./
```

Calibration and profiling requires a SMU from Keithley. Our tests and initial calibration are done with a *Keithley 2604B SourceMeter* connected via ethernet. The shepherd-cape has be installed on a beaglebone running the latest shepherd-software and also be accessible via ethernet.

## Usage

The Interface is not stable ATM, so explore the commands on your own:

```Shell
# to see the commands:
shepherd-cal --help
# help for individual commands, ie:
shepherd-cal calibration -h
shepherd-cal calibration measure -h
shepherd-cal profile -h
```

It is currently possible to

- calibrate the shepherd cape
- read and write calibration to the shepherd cape
- profile the analog frontends (harvester & emulator)
- analyze the profiles with resulting statistics and plots

For actual measurements the program will tell you how to connect the SMU to the cape correctly.

## Examples

Calibration

```Shell
shepherd-cal calibration measure sheep0 --user jane --password 1234 --smu-ip 10.0.0.41 -o sheep0_cape_v240b.yml
shepherd-cal calibration write sheep0 -u jane -p 1234 -m sheep0_cape_v240b.yml -v 24B0 -s i1270057 -d 2022-11-11
```

Profiling

```Shell
shepherd-cal profile measure sheep0 -u jane -p 1234 --smu-ip 10.0.0.41
shepherd-cal profile analyze -o stats.csv --plot
```
