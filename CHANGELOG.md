# History of Changes

## 0.9.1

- adapt to latest naming-changes in core-lib
  - established `ivsurface` and `ivtrace` instead of curves and sample
  - use `Reader.read()` instead of `.read_buffer()`
  - use `Reader.CHUNK_SAMPLES_N`, `Reader.chunks_n`, instead of .buffer_xyz
  - use `UartLogger` instead of #Tracer
- programmer: detect and handle hanging startup
- `GPIOTracer` - implement masking
  - sheep adapts mask to current cape and writes it to PRU
- herd: improve config-finding -> [see doc](https://orgua.github.io/shepherd/tools/herd.html#static-config)
- doc: rip out documentation for public instance -> <https://nes-lab.github.io/shepherd-nova/>
- workflows: general improvements
- **tested**: pytest sheep, pytest herd linux & windows
- **outdated**: Py VSrc shared lib, most of doc,

## 0.9.0

The main motivation was the replacement of the flawed segmented ring-buffer to a) remove a performance-bottleneck and b) increase reliability.
This unlocked and triggered a lot of other improvements in both regards.

- Buffer replacement
  - old system: 64x 0.1 s segments, bidirectional, 2^14 embedded gpio-events in each segment
  - new: input, output, gpio and utilization has their own buffer
  - input buffer is now also automatically cached in a 64kB OCMC-Section. This allows PRU0 to fetch data itself, but the kernel module must fill it in time (8x 10ms sections) otherwise the PRU has to access the (slow) RAM (reads could be stalled up to 7 us for 8 byte)
  - lots overhead is removed from PRU (more consistent sample-duration), a buffer exchange on the old firmware could cause utilization of >110%
  - kernel module is able to fill OCMC-Cache even with high CPU load! and task overhead is rather small (<5% load)
  - find sweetspots for buffersizes to maximize GPIO-Recording, but don't harm normal operation. RAM-Area is limited to 48 MB, where GPIO now takes 32 MB instead of initially 10
  - added loopback-unittest: fileInp - py - ram - cache - pru - ram - py - fileOut
  - cached buffer is fully verified (correctness via loopback, high load scenario, overhead-estimation on all sub-systems)
- GPIO-Recording
  - gpio-recording is consistent now (race condition in software-mutex), closes #57
  - as GPIO-Sampling-Rate is higher than recording-capability, the system senses back-pressure and drops gpio-samples if buffers are about to overflow
  - worst read-speed was ~ 120 kHz before (1.75 MHz mean, 1.9 MHz max) because PRU1 had to fetch input-buffer for PRU0
  - just READ: min 1.429, mean 2.26, max 2.976 MHz (new sync and util1-stats)
  - always WRITE: min 1.152, mean 1.605, max 1.701 MHz, 112 ns check, 172 ns write
  - pru1 reports 704 ns as worst loop (1.420 MHz), without debug 660 ns (1.515 MHz)
- vPowerSource
  - Emulation from ivsamples uses now 78 % PRU0 (mean), at most 80 % (max)
  - emu with harvesting (from IVSurface) uses 86 % PRU0, at most 89 %  (max)
  - add prototype of battery-model to PRU and also integrate config into shared RAM
  - vharvester - improve similarity to VOC-search by jumping to VOC
- timesync
  - overhaul with big performance improvements, includes an accompanying simulation (in kernel-source) and behaves very similar in reality, fixes #19
  - PI-Algorithm with proper warning via kernel logs (adaptive tuning - 3 stages of accuracy - via error-boundaries)
  - timesync on hardware-level has reached lower boundary as ktime_get_real(), the fastest way to get the time, takes 332 ns
  - PRU uses timer-compensation to slow-down/speed-up (clock-skew with bresenham-algo)
  - improve initial sync for quicker convergence
  - timestamp handling of PRU is supervised by kMod (warn & correct)
  - fix unequal ChipSelect-distance on sync-wrap
- extend Warning-System with the goal to supervise and self-diagnose every critical element during operation
  - timesync: PTP, PHC2SYS and Sys-to-PRU-sync is recorded and faulty states are detected and reported as warning
  - for lab-use NTP is also recorded
  - PRU: utilization of mean and max loop-duration is recorded and broken real-time-condition is reported
  - System-Stats are recorded: CPU-Util, NW-rates, IO-rates, RAM-usage
  - kernel and sheep logs are also recorded
  - PRU errors get reported up the chain and unplanned restarts trigger exceptions
  - if possible the exact timestamps from the reporting services are used
  - buffer-supervisor to detect backpressure, overflows (writer overtakes reader), harmed canaries
  - experiment-supervisor to detect if recorder missed start or ended too early
  - canaries (4 in buffers, 12 in shared memory)
- PRU
  - more direct memory access (before it had 2 layers of pointer-translation)
  - overhaul of state-machines, remove mutexes
  - clean up build system
  - unify message-system
  - cores record their own util-stats
- KernelModule
  - more correct and modern usage of kernel-API
  - cleaner start/stop of submodules
  - periodically check canaries
  - access and fill-routines for OCMC-cache (fast intermediate buffer)
  - bind io-mem without cache
- PythonSheep
  - more modular code (most files now < 500 LOC)
  - new data-flow: source dictates the chunk-size, the sink deals with it (or complains early)
  - progress-bar during filling initial buffer and during experiment
  - buffers get monitored to detect back-pressure (and react to it)
  - detector for buffer overflows and possible blind spots during detection (low polling rate)
  - optimize write operation for GPIO - resulting in 3x more throughput - from 9M Events to ~ 26M in 60 s
  - Benchmark writing full gpio-load, with lots of discarded buffer-segments
    - full-lzf, 60s, 13.3M GPIO, 105 MB
    - gpio-None, 60s, 22.6M GPIO, 257 MB
    - full-None, 60s, 26.0M+ GPIO, 356 MB, all on external uSD (36M discarded)
  - repaired unittests
  - make set_stop() & set_start() safer, less prone to raise
- GitHub-Actions
  - also test herd on windows & macOS
  - extend tests to python 3.13
  - release via tagging
  - more modular, sub-jobs getting triggered by action
  - prepare release to pypi via trusted publishing

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
  - fix ingestion of ivsurface / curves (windowsize was not propagated)
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
- harvesting ivsurface / curves
  - fix max age of samples
  - improve initial interval_step to intake two whole curves of the IVSurface before reset
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
