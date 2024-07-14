# History of Changes

## 0.8.1

- sheep - limit pru-warning count
- sheep - fix stopping of ntp-service 
- py - add progressbars to long processes
- py - don't limit pandas to <v2 anymore
- herd - query for alive status of testbed (all hosts responding)
- herd - more robust unittesting
- extend ruff and fix ~ 200 linting-errors 

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
  - allow analyzing recorded gpio sync traces (`software/time_sync_analyzer`)
- update floorplan of testbed
- add tooling to allow analyzing timesync-behavior (software/time_sync_analyzer)
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
