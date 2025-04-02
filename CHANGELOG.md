# History of Changes

## 0.8.5

- sheep bugfix that prevented clean exit after execution (unhandled filled queue did not release thread)
- hw-designfiles - add cape 2.5e & move prior capes to `_deprecated`

## 0.8.4

- sheep programming needed some improvements
  - bugfix - don't realign nrf-hex-file with 16bit address limit
  - workaround - reduce default data-rate for programming (500k to 200k)
  - bugfix - properly report programming errors (write-error, verify, parsing was not reported correctly)
  - ihex - added remaining 3 of 6 command-types of intel hex
  - ihex - corrected calculation of Extended Segment Address
  - ihex - more detailed error-reporting in python (including line-number)
  - ihex - full 32bit address-space should now be usable (was limited to <64k before)
  - ihex - detection of malformed command records
  - ihex - detection of unknown commands (throw error)
  - error-reporting did not detect a pru-restart
  - programmer now retries 5 times before failing
    - also the data-rate gets reduced by ~~20~~ 40 % after each failed attempt
- sheep
  - now logs usage (timestamp, sub-command i.e. `run`, total runtime)
  - `shepherd-sheep eeprom read -f` prints full data-model
  - `shepherd-sheep eeprom read -r` prints only hardware revision of cape
  - small optimizations (fail early, but avoid exception; avoid code duplication)
- herd
  - fix bug on Windows OS while distributing files
  - use PurePosixPath for all remote paths (better cross-compatibility)
  - some run_cmd() executions have been silenced (from info to debug-level)
  - `shepherd-herd retrieve` now alternatively takes local task/job-file and fetches embedded paths
  - `shepherd-herd retrieve` does not add hostname to filename if already present
  - `shepherd-herd alive` had a bug and reported the opposite
  - `shepherd-herd status` now also reports last testbed-usage as timestamp and timedelta
- python
  - avoid os-package if pathlib can handle it
  - avoid sys.exit() if click.context.exit() is available
- hw-designfiles - add cape 2.5d & move prior capes to `_deprecated`
- ansible - avoid updating kernel
- **tested**: pytest sheep, pytest herd linux & windows

## 0.8.3

- setup
  - fix ambitious removal of ciphers for secure host
  - test and adapt to raspberry pi OS
  - create smaller playbook to redeploy roles (`dev_redeploy_roles.yml`)
- herd
  - fix StringIO-Bug
- timesync: improve configuration for client and server
- sync analysis: move to `software/debug_analyze_time_sync` and also add CLI
- vsrc comparison: move to `software/debug_compare_vsrouces`
- py
  - fix > 100 linting error
  - improve exception-system
  - make compatible with latest core-lib 2024.11.3
- pru
  - extend error-system
  - refactor and fix messaging-system
- **tested**: pytest sheep, pytest herd, playbook dev_rebuild_sw.yml

## 0.8.2

- PRU now gets partially zeroed buffer-segments
- PRU had a race-condition with a loose mutex resulting in keeping old gpio-samples
- python warns on full gpio-buffer (as it can only hold ~16k entries in 100 ms)
- python warns if first or last timestamp of gpio-buffer is out of scope of outer buffer-period
- hw cape - add errata-list
- vsrc - add datatype to determine state-variables
- CalibrationPair - add units
- split pru0-shepherd-fw into hrv & emu -> kModule, shepherd-sheep, playbooks, workflows adapted
- pru-vsource - add feedback to harvester
- pru-harvester - add feedback & extrapolation for cv-harvester
- **tested**: pytest sheep, pytest herd, playbook dev_rebuild_sw.yml

## 0.8.1

- big bugfix release
- sheep
  - limit pru-warning count
  - fix forced stopping of ntp-service
  - improve debug-output
  - fix ingestion of ivcurves (windowsize was not propagated)
  - fix copy of emu-input into shared mem (off-by-one-error)
- herd
  - query for alive status of testbed (all hosts responding)
  - more robust unittesting
  - add automated benchmark in `software\shepherd-herd\test_manual\`
- python in general
  - add progress-bars to long processes
  - remove progress-bar after task finishes (most)
  - don't limit pandas to <v2 anymore
  - prepare for py313
- pru vsourve & harvester
  - fix residue feature
  - remove limiting-behavior of boost-regulator
  - fix calculation of window_size for individual usecases
  - ivcurve - cutout measurements during big step
  - improve code-quality (cleaner fetching of emu-input and special math-functions are easier to understand)
- harvesting ivcurves
  - fix max age of samples
  - improve initial interval_step to intake two whole ivcurves before reset
  - improve VOC-harvester
- python module "shepherd-pru" interfaces pru-c-code via ctypes
  - harvesting & emulation can be done
  - benchmarking revealed some bugs
- remove cython-playground (in favor of ctypes-implementation)
- ansible: remove py-packages before install
- extend ruff and fix ~ 200 linting-errors
- **tested**: pytest sheep, pytest herd, playbook dev_rebuild_sw.yml

## 0.8.0

- linux
  - ~optimize for real-time kernel~, moved to branch
  - make phc2sys & ptp4l more reliable
  - test and optimize for debian 12.6 bookworm
    - harvest cpu-usage drops from 69% (py310) to 61% (py311)
- kernel-module
  - cleanup, optimize
  - more futureproof (use ktime_get_X() instead of getnstimeofday())
  - remove mutex (seems to have deadlocked sometimes)
  - fix hrtimer_forward()-usage (source for instability)
  - more const-correctness
  - can now change firmware of both PRUs
  - more pru-messages are handed to python (for logging)
  - warn/error if sync-config is wrong
- python
  - reduce load by 50 % (omit timestamps & change compression)
  - IV-Stream -> add meta-data for stored buffer-segment
    - meta: buffer-timestamp, sample-count, pru-util mean & max
    - this can reconstruct timestamp-stream after the measurement
  - refactored h5writer into smaller modules (monitor and recorder threads)
  - added monitors for uart, pru-usage, ptp-status
  - replaced setup.cfg by pyproject.toml with ini2toml
  - added heartbeat-messages during operation
  - fix launcher - was misbehaving with 100% cpu-usage
  - added watchdog-reset service - functionality was in launcher before
  - reduced ram-usage of services
  - removed scipy-dependency (less ram usage, faster startup)
  - disable NTP before starting a measurement
- herd
  - resync - give info about time-diff
  - improve interpretation of sheep-exit-codes
- ansible
  - major overhaul
  - more removed packages during cleanup
  - safer kernel-downgrading
  - faster code
  - safer firmware-removal
  - disable unwanted services
- toolchain: replace isort, black, flake8, pylint by ruff
- debug
  - add option to generate kernel gpio edges (`trigger_loop_callback()` in `pru_sync_control.c`)
  - allow analyzing recorded gpio sync traces (`software/debug_analyze_time_sync`)
- update floorplan of testbed
- add tooling to allow analyzing timesync-behavior (software/debug_analyze_time_sync)
- add current hardware design files
- major overhaul documentation
- **tested (fully)**: pytest sheep, pytest herd, ansible install
- ready-to-use image will be created - look in getting-started guide

## 0.7.1

- python
  - speed improvements, linting, simplifications
  - optimize for py310..py312
  - safer sheep-shutdown
  - fully type-hinted
  - more error-catching
  - more responsive monitor-threads
  - identify and try to avoid deadlocks and infinite loops
- improve timesync reliability (phc2sys & ptp4l)
- forbid unsafe ssh cypher
- update deps

## 0.7.0

- pru-firmware:
   - improve blind-spots of gpio-sampling
   - fix compiler warning (cgt & gcc)
   - [measure timings](https://github.com/orgua/shepherd_v2_planning/blob/main/scratch/pruBenchmark_2023_10.md)
   - bugfixes
- sheep
   - refactoring of monitors
   - repair ptp & dmesg / kernel logging
   - repair uart-monitor
   - allow to record stdout of sheep
   - set gpio-direction to input for now
   - redo logging-system
- herd
   - more reliable (needs to enter context now)
   - tests availability of nodes / sheep
   - redo logging-system
   - refactor
   - improve doc
   - more functionality in herd-class
- doc
   - improve details
   - add info about testbed and subprojects
- ansible
   - tweaks, speedups
   - fixes
   - (timesync) services are now more reliable
   - update kernel version
   - lots of linting
   - script to activate emmc-flasher
- cal
   - lots of tweaks and fixes
- **tested**: ansible-installer, herd, sheep

## v0.4.5 - 2023.08.23

- add option to build an inventory
- herd, sheep, cal-tool: fully integrate datalib
- sheep
  - improve exit behavior
  - various small improvements, refactorings
  - speed-improvements through tracing
- ansible:
  - safer pipes
  - bugfixes
- pru-programmer: bugfixes, add direction pin, test with new target
- integrate other shepherd-projects as submodules
- ubuntu 22.04 now default distribution for sheep (py 3.10)
- cal-tool uses typer for cli now
- **tested**: shepherd-sheep & -herd

## 0.4.4 - 2023.02.26
