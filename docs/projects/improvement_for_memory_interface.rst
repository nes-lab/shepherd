Memory Interface
=================

*Improvements for the Memory Interface between PRU and user space*

Introduction
------------

- shepherd consists of an embedded linux board (beaglebone black) that has an arm-core and special real time units (two co-processors called PRU)
- there are two basic functions for shepherd:

  - harvesting / recording an energy source
  - emulating that energy environment for a connected wireless node (target MCU)

- focus is on the emulation part as this is most constrained
- the PRUs are sampling an ADC, writing to a DAC and reading GPIO … and calculating some real-time math (virtual power source)
- the linux side is controlled by a python-program that has a direct memory interface to the PRUs -> that program supplies input data and collects the resulting measurement stream
- (side-info) there is an optional second communication channel to a kernel module (python and PRU can each talk to that module) controlling most of the state-machine

- Problem: the memory interface for exchanging that described measurement-data has some design-flaws described in "Current Situation" and "Known Constraints" below

Current Situation
-----------------

- overly complicated and "expensive" borrow & return system with a 64 segment ringbuffer (SampleBuffer)
- SampleBuffer currently holds 100 ms of data (10 kSamples) and gpio-samples
- nested gpio-struct (GPIOEdges) inside SampleBuffer holds only ~ 16 kSamples -> artificial bottleneck
- current trick / dirty hack as real time constraints got violated from time to time (when reading from RAM took to long): pru1 does the reading from RAM now and shares data via fast shared RAM (exclusive for PRUs) for pru0

Timings for reference (emulation, data from mid 2021):

- 10'000 ns for each loop (@ 100 kHz) available for getting data, process it and writing data
- ~600 ns for reading the ADC (current-value)
- 400 - 3'000 ns for reading data from RAM
- ~ 8'000 ns for the virtual source calculations (worst case)
- ~ 800 ns for buffer-swap (only every 100 ms)

   - 400 ns prepare buffer
   - 200 ns mutex-part / gpio-swap
   - 200 ns send full buffer

- 720 ns for writing to DAC

Goals
-----

- our goal is to remove overhead, bottle-necks and boost the performance mainly for the gpio sampling to reliable frequencies in the range of 8 - 16 MHz
- the gpio sampling is currently varying from 840 kHz to 5.7 MHz with a mean of 2.2 MHz
- the main point of attack will be

  - the design of a new memory interface (buffer-design)
  - redesign of the state-machine coordinating the measurement (time-sync, buffer swap, controlling measurement-states)
  - maybe: improved sampling routines for the ICs (bitbanged SPI in assembler)

- another possibility for high throughput gpio-sampling

  - offer two firmwares: virtual source emulation with slower GPIO-Sampling OR
  - disable the virtual power source that is occupying > 90% of PRU0

Known Constraints
-----------------

- roughly 1 MB/s in both directions over the mem-interface (for emulation / power traces)
- event based gpio-sampling with high throughput might overburden beaglebone, example:

  - 1 MBaud Serial might cause 1 * 10^6 events
  - event consists of 2 byte gpio-register & 8 byte timestamp
  - 10 byte @ 1 MHz are ~ 10 MB/s

- Note: there is another Testbed called Flocklab, that is also using the Beaglebone. They sample serial via a serial-kernel-module and are limited at ~ .5 to 1 MBaud which produces high system load
- the PRU is good at writing into (system) RAM with just 1 cycle, but slow at reading with 100-600 cycles per read (at 200 MHz PRU baseclock)

  - by using memcopy one read can be larger than uint32, by only needing little more time
  - currently the PRU reads the voltage- and current-value in two OPs (design-flaw)

- PRUs have only 8 kB private RAM and 12 kB shared RAM (between the two PRUs)
- there might be more …

Hardware Needed
---------------

- BeagleBone, Power-Adapter
- SD-Card & SD-Cardreader for flashing a Linux-Image
- Network-Cable and external router or switch to connect via ssh
- logic-analyzer to determine timings of subroutines
- dev PC with shell (linux preferred, but WSL, Powershell or MacOS-Shell also work)

Milestones
----------

- prototype idea (drawing, text or mockup prototype)
- setup hardware
- rough implementation
- testing phase
- finale implementation

Links to Code
-------------

- `mem-interface struct in c <https://github.com/orgua/shepherd/blob/main/software/firmware/include/commons.h#L127>`_
- `buffer-swap in c <https://github.com/orgua/shepherd/blob/main/software/firmware/pru0-shepherd-fw/main.c#L91>`_
- `buffer reception in python <https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd/shepherd_io.py#L134>`_
- `buffer swap routines (return_buffer() & get_buffer()) in python <https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd/shepherd_io.py#L715>`_
- `kernel module <https://github.com/orgua/shepherd/tree/main/software/kernel-module/src>`_


External BBone-Projects that may help:

- `BeagleLogic <https://theembeddedkitchen.net/beaglelogic-building-a-logic-analyzer-with-the-prus-part-1/449>`_
- `Rocketlogger <https://rocketlogger.ethz.ch/>`_
