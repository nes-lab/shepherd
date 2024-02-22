# Time-Sync - Analyzer-Tool

**Main Documentation**: <https://orgua.github.io/shepherd>

**Source Code**: <https://github.com/orgua/shepherd/tree/main/software/time_sync_analyzer>

---

Collection of tools to analyze Sync-behavior, recorded with a Saleae Logic Pro.

The measurement-process to get the actual data is described in the dev-guide of the official [documentation](https://orgua.github.io/shepherd).

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

```
Time[s], Channel 0, Channel 1
0.000000000000000, 1, 1
7.642110550000000, 1, 0
```

**Note**: Names of channels are ignored by the tool

## Run Analysis

This tool has no proper CLI for now. 
Copy the `csv`-data into the `./example`-directory or where the `sync_1channel`-script located and run the script

```shell
python3 sync_1channel
```

## Extras

Creating CPU-Load

- run harvest first (this will create a measurement file)
- after that you can run emulation that uses that exact file as input
- Note: we exclude sheep0, as it is the ptp-server

```Shell
shepherd-herd -v --limit sheep1,sheep2, run --attach .\software\time_sync_analyzer\config_harvest.yaml
shepherd-herd -v --limit sheep1,sheep2, run --attach .\software\time_sync_analyzer\config_emulation.yaml
```
