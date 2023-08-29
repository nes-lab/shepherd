# Data Module

[![PyPiVersion](https://img.shields.io/pypi/v/shepherd_data.svg)](https://pypi.org/project/shepherd_data)
[![Pytest](https://github.com/orgua/shepherd-datalib/actions/workflows/python-app.yml/badge.svg)](https://github.com/orgua/shepherd-datalib/actions/workflows/python-app.yml)
[![CodeStyle](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**Documentation**: <https://orgua.github.io/shepherd/external/shepherd_data.html>

**Source Code**: <https://github.com/orgua/shepherd-datalib>

**Main Project**: <https://github.com/orgua/shepherd>

---

This Python Module eases the handling of hdf5-recordings used by the [shepherd](https://github.com/orgua/shepherd)-testbed. Users can read, validate and create files and also extract, down-sample and plot information.

## Installation

### PIP - Online

```shell
pip3 install shepherd-data -U
```

For bleeding-edge-features or dev-work it is possible to install directly from GitHub-Sources (here `dev`-branch):

```Shell
pip install git+https://github.com/orgua/shepherd-datalib.git@dev#subdirectory=shepherd_data -U
```

## Programming Interface

### Basic Usage (recommendation)

```python
import shepherd_data as shpd

with shpd.Reader("./hrv_sawtooth_1h.h5") as db:
    print(f"Mode: {db.get_mode()}")
    print(f"Window: {db.get_window_samples()}")
    print(f"Config: {db.get_config()}")
```

### Available Functionality

- `Reader()`
  - file can be checked for plausibility and validity (`is_valid()`)
  - internal structure of h5file (`get_metadata()` or `save_metadata()` ... to yaml) with lots of additional data
  - access data and various converters, calculators
    - `read_buffers()` -> generator that provides one buffer per call, can be configured on first call
    - `get_calibration_data()`
    - `get_windows_samples()`
    - `get_mode()`
    - `get_config()`
    - direct access to root h5-structure via `reader['element']`
    - converters for raw / physical units: `si_to_raw()` & `raw_to_si()`
    - `energy()` sums up recorded power over time
  - `downsample()` (if needed) visualize recording (`plot_to_file()`)
- `Writer()`
  - inherits all functionality from Reader
  - `append_iv_data_raw()`
  - `append_iv_data_si()`
  - `set_config()`
  - `set_windows_samples()`
- IVonne Reader
  - `convert_2_ivcurves()` converts ivonne-recording into a shepherd ivcurve
  - `upsample_2_isc_voc()` TODO: for now a upsampled but unusable version of samples of short-circuit-current and open-circuit-voltage
  - `convert_2_ivsamples()` already applies a simple harvesting-algo and creates ivsamples
- `./examples/`
  - `example_convert_ivonne.py` converts IVonne recording (`jogging_10m.iv`) to shepherd ivcurves, NOTE: slow implementation
  - `example_extract_logs.py` is analyzing all files in directory, saves logging-data and calculates cpu-load and data-rate
  - `example_generate_sawtooth.py` is using Writer to generate a 60s ramp with 1h repetition and uses Reader to dump metadata of that file
  - `example_plot_traces.py` demos some mpl-plots with various zoom levels
  - `example_repair_recordings.py` makes old recordings from shepherd 1.x fit for v2
  - `jogging_10m.iv`
      - 50 Hz measurement with Short-Circuit-Current and two other parameters
      - recorded with "IVonne"

### Functionality Update (WIP)

- `BaseReader`
  - `__repr__()`
  - `read_buffers`
  - `get_calibration_data`
  - `get_window_samples`
  - `get_mode`
  - `get_config`
  - `get_hostname`
  - `get_datatype`
  - `get_hrv_config`
  - `is_valid`
  - `energy()`
  - `check_timediffs()`
  - `data_timediffs()`
  - `get_metadata()`
  - `save_metadata()`

- `BaseWriter(BaseReader)`
  - `append_iv_data_raw`
  - `append_iv_data_si`
  - `store_config`
  - `store_hostname`

- `Reader(BaseReader)`
  - `save_csv()`
  - `save_log()`
  - `downsample()`
  - `resample()`
  - `generate_plot_data()`
  - `assemble_plot()`
  - `plot_to_file()`
  - `multiplot_to_file()`

- `Writer(BaseWriter)`
  - (no extending methods)

## CLI-Interface

After installing the module the datalib offers some often needed functionality on the command line:

**Validate Recordings**

- takes a file or directory as an argument

```shell
shepherd-data validate dir_or_file

# examples:
shepherd-data validate ./
shepherd-data validate hrv_saw_1h.h5
```

**Extract IV-Samples to csv**

- takes a file or directory as an argument
- can take down-sample-factor as an argument

```shell
shepherd-data extract [-f ds-factor] [-s separator_symbol] dir_or_file

# examples:
shepherd-data extract ./
shepherd-data extract -f 1000 -s ; hrv_saw_1h.h5
```

**Extract meta-data and sys-logs**

- takes a file or directory as an argument

```shell
shepherd-data extract-meta dir_or_file

# examples:
shepherd-data extract-meta ./
shepherd-data extract-meta hrv_saw_1h.h5
```

**Plot IVSamples**

- takes a file or directory as an argument
- can take start- and end-time as an argument
- can take image-width and -height as an argument

```shell
shepherd-data plot [-s start_time] [-e end_time] [-w plot_width] [-h plot_height] [--multiplot] dir_or_file

# examples:
shepherd-data plot --multiplot ./
shepherd-data plot -s10 -e20 hrv_saw_1h.h5
```

**Downsample IVSamples (for later GUI-usage, TODO)**

- generates a set of downsamplings (20 kHz to 0.1 Hz in x4 to x5 Steps)
- takes a file or directory as an argument
- can take down-sample-factor as an argument

```shell
shepherd-data downsample [-f ds-factor] [-r sample-rate] dir_or_file

# examples:
shepherd-data downsample ./
shepherd-data downsample -f 1000 hrv_saw_1h.h5
shepherd-data downsample -r 100 hrv_saw_1h.h5
```

## Data-Layout and Design choices

Details about the file-structure can be found in the [main-project](https://github.com/orgua/shepherd/blob/main/docs/user/data_format.rst).

TODO:
- update design of file
- data dtype, mode, ...

### Modes and Datatypes

- Mode `harvester` recorded a harvesting-source like solar with one of various algorithms
  - Datatype `ivsample` is directly usable by shepherd, input for virtual source / converter
  - Datatype `ivcurve` is directly usable by shepherd, input for a virtual harvester (output are ivsamples)
  - Datatype `isc_voc` is specially for solar-cells and needs to be (at least) transformed into ivcurves later
- Mode `emulator` replayed a harvester-recording through a virtual converter and supplied a target while recording the power-consumption
  - Datatype `ivsample` is the only output of this mode

### Compression & Beaglebone

- supported are uncompressed, lzf and gzip with level 1 (order of recommendation)
  - lzf seems better-suited due to lower load, or if space isn't a constraint: uncompressed (None as argument)
  - note: lzf seems to cause trouble with some third party hdf5-tools
  - compression is a heavy load for the beaglebone, but it got more performant with recent python-versions
- size-experiment A: 24 h of ramping / sawtooth (data is repetitive with 1 minute ramp)
  - gzip-1: 49'646 MiB -> 588 KiB/s
  - lzf: 106'445 MiB -> 1262 KiB/s
  - uncompressed: 131'928 MiB -> 1564 KiB/s
- cpu-load-experiments (input is 24h sawtooth, python 3.10 with most recent libs as of 2022-04)
  - warning: gpio-traffic and other logging-data can cause lots of load

```
  emu_120s_gz1_to_gz1.h5 	-> emulator, cpu_util [%] = 65.59, data-rate =  352.0 KiB/s
  emu_120s_gz1_to_lzf.h5 	-> emulator, cpu_util [%] = 57.37, data-rate =  686.0 KiB/s
  emu_120s_gz1_to_unc.h5 	-> emulator, cpu_util [%] = 53.63, data-rate = 1564.0 KiB/s
  emu_120s_lzf_to_gz1.h5 	-> emulator, cpu_util [%] = 63.18, data-rate =  352.0 KiB/s
  emu_120s_lzf_to_lzf.h5 	-> emulator, cpu_util [%] = 58.60, data-rate =  686.0 KiB/s
  emu_120s_lzf_to_unc.h5 	-> emulator, cpu_util [%] = 55.75, data-rate = 1564.0 KiB/s
  emu_120s_unc_to_gz1.h5 	-> emulator, cpu_util [%] = 63.84, data-rate =  351.0 KiB/s
  emu_120s_unc_to_lzf.h5 	-> emulator, cpu_util [%] = 57.28, data-rate =  686.0 KiB/s
  emu_120s_unc_to_unc.h5 	-> emulator, cpu_util [%] = 51.69, data-rate = 1564.0 KiB/s
```
