# History of Changes

## 0.7.2

- linux
  - switch to real-time kernel
  - make phc2sys & ptp4l more reliable
- kernel-module
  - cleanup, optimize
  - more futureproof
- python
  - reduce load by 50 % (omit timestamps & change compression)
- toolchain
  - replace isort, black, flake8 by ruff
- debug
  - add option to generate kernel gpio edges (`trigger_loop_callback()` in `pru_sync_control.c`)
  - allow analyzing recorded gpio sync traces (`software/test_timesync`)
- update floorplan of testbed

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
