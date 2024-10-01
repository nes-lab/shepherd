# Time-Sync - Analyzer-Tool

**Main Documentation**: <https://orgua.github.io/shepherd>

**Source Code**: <https://github.com/orgua/shepherd/tree/main/software/debug_analyze_time_sync>

---

Collection of tools to analyze Sync-behavior, recorded with a Saleae Logic Pro.

The measurement-process to get the actual data is described in the dev-guide of the official [documentation](https://orgua.github.io/shepherd).

## Installation

Similar to the other python tooling you can run

```Shell
git clone https://github.com/orgua/shepherd
cd shepherd/software/debug_analyze_time_sync
pip install .
```

This assumes that python > v3.10 and git are installed

For install directly from GitHub-Sources (here `dev`-branch):

```Shell
 pip install git+https://github.com/orgua/shepherd.git@dev#subdirectory=software/debug_analyze_time_sync -U
```

## Expected Data-Format

```
Time[s], Channel 0, Channel 1
0.000000000000000, 1, 1
7.642110550000000, 1, 0
```

**Note**: Names of channels are ignored by the tool

## Run Analysis

This tool has a minimalistic CLI.
Either change into the directory that contains the measurements or provide the path to the tool via the `-i`-parameter.
Extra options and help will be listed by issuing `--help`.

```shell
sync-analysis -i ./path_to_data

# OR
cd ./path_to_data
sync-analysis
```

## Extras

Creating CPU-Load

- run harvest first (this will create a measurement file)
- after that you can run emulation that uses that exact file as input
- Note: we exclude sheep0, as it is the ptp-server

```Shell
shepherd-herd -v --limit sheep1,sheep2, run --attach .\software\debug_analyze_time_sync\config_harvest.yaml
shepherd-herd -v --limit sheep1,sheep2, run --attach .\software\debug_analyze_time_sync\config_emulation.yaml
```
