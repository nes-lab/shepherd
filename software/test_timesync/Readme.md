# Sync-Analyzer

Collection of tools to analyze Sync-behavior, recorded with saleae logic pro.

The process to get the actual data is described in separate chapters:

- [prepare software](../../docs/time_sync/1_prepare_software.md)
- [set up hardware](../../docs/time_sync/2_setup_hardware.md)
- [run measurements](../../docs/time_sync/3_measurement.md)
- [analysis](../../docs/time_sync/4_analysis.md)

It is part of the official [documentation](https://orgua.github.io/shepherd).

## Installation

Similar to the other python tooling you can run

```Shell
git clone https://github.com/orgua/shepherd
cd shepherd/software/test-timesync
pip install .
```

This assumes that python > v3.10 and git are installed

For install directly from GitHub-Sources (here `dev`-branch):

```Shell
 pip install git+https://github.com/orgua/shepherd.git@dev#subdirectory=software/test-timesync -U
```

## Expected Data-Format

```csv
Time[s], Channel 0, Channel 1
0.000000000000000, 1, 1
7.642110550000000, 1, 0
```

Note: Name of channels is ignored

## Software

Creating CPU-Load

- run harvest first (this will create a measurement file)
- after that you can run emulation that uses that exact file as input
- Note: we exclude sheep0, as it is the ptp-server

```Shell
shepherd-herd -v --limit sheep1,sheep2, run --attach .\software\test_timesync\config_harvest.yaml
shepherd-herd -v --limit sheep1,sheep2, run --attach .\software\test_timesync\config_emulation.yaml
```
