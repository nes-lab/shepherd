Improvements for the Memory Interface between PRU and user space
================================================================

Introduction
------------

- shepherd consists of an embedded linux board (beaglebone black) that has an arm-core and special real time units (two co-processors called PRU)
- there are two basic functions for shepherd:

  - harvesting / recording an energy source
  - emulating that energy environment for a connected wireless node (target MCU)

- focus is on the emulation part as this is most constrained
- the PRUs are sampling an ADC, writing to a DAC and reading GPIO .... and calculating some real-time math stuff (virtual power source)
- the linux side is controlled by a python-program that has a direct memory interface to the PRUs -> that program supplies input data and collects the resulting measurement stream
- (side-info) there is an optional second communication channel to a kernel module (python and PRU can each talk to that module) controlling most of the state-machine

Current Situation
-----------------

- overly complicated borrow & return system with a 64 segment ringbuffer (SampleBuffer)
- SampleBuffer currently holds 0.1 s of data (10 kSamples) and gpio-samples
- nested gpio-struct (GPIOEdges) inside SampleBuffer holds ~ 16 kSamples -> artificial bottleneck

Goals
-----

- our goal is to remove bottle-necks and boost the performance mainly for the gpio sampling to reliable frequencies, hopefully in the range of 8 - 16 MHz
- the gpio sampling is currently varying from 840 kHz to 5.7 MHz with a mean of 2.2 MHz
- the main point of attack will be

  - the design of a new memory interface
  - redesign of the state-machine coordinating the measurement (time-sync, buffer swap, controlling measurement-states)
  - improved sampling routines for the ICs (currently bitbanged SPI in assembler)

- another possibility for high throughput gpio-sampling -> disable the virtual power source that is occupying > 90% of PRU0

Known Constraints
-----------------

- roughly 1 MB/s in both directions over the mem-interface (for emulation / power traces)
- event based gpio-sampling with high throughput might overburden beaglebone, example:

  - 1 MBaud Serial might cause 1 * 10^6 events
  - event consists of 2 byte gpio-register & 8 byte timestamp
  - 10 byte @ 1 MHz are ~ 10 MB/s

- the PRU is good at writing into RAM with just 1 cycle, but slow at reading with 100-600 cycles per read (at 200 MHz PRU baseclock)

  - by using memcopy one read can be larger than uint32, by only needing little more time

- PRUs have only 8 kB private RAM and 12 kB shared RAM (between the two PRUs)
- there might be more ...

Hardware Needed
---------------

- BeagleBone, Power-Adapter
- SD-Card & SD-Cardreader for flashing a Linux-Image
- Network-Cable and external router or switch to connect via ssh
- logic-analyzer to determine timings of subroutines
- dev PC with shell (linux preferred, but WSL, Powershell or MacOS-Shell also work)

Links to Code
-------------

- `mem-interface struct in c <https://github.com/orgua/shepherd/blob/main/software/firmware/include/commons.h#L127>`_
- `buffer-swap in c <https://github.com/orgua/shepherd/blob/main/software/firmware/pru0-shepherd-fw/main.c#L91>`_
- `buffer reception in python <https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd/shepherd_io.py#L134>`_
- `kernel module <https://github.com/orgua/shepherd/tree/main/software/kernel-module/src>`_

External BBone-Projects that may help:

- `BeagleLogic <https://theembeddedkitchen.net/beaglelogic-building-a-logic-analyzer-with-the-prus-part-1/449>`_
- `Rocketlogger <https://rocketlogger.ethz.ch/>`_
