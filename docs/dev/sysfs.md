# SYSFS interface

The shepherd kernel module provides a user interface that exposes relevant parameters and allows control of the state of the underlying shepherd engine consisting of the kernel module and the firmware running on the two PRU cores. When the module is loaded, the interface is available under `/sys/shepherd`

## Basic Functionality

```{caution}
OUT OF DATA
```

- `state`: current state of the pru state-machine, mostly `idle` or `running`, plus some transitional states. Also used to control the PRU by setting `start` or `stop`.
- `mode`: can be either `emulator` or `harvester` and some debug-modes
- `n_buffers`: The maximum number of buffers used in the data exchange protocol
- `BUFFER_SAMPLES_N`: The number of samples contained in one buffer. Each sample consists of a current and a voltage value.
- `buffer_period_ns`: Time period of one 'buffer'. Defines the sampling rate together with `BUFFER_SAMPLES_N`
- `memory/address`: Physical address of the shared memory area that contains all `n_buffers` data buffers used to exchange data
- `memory/size`: Size of the shared memory area in bytes
- `pru_msg_box`: in and out message box to communicate with the PRUs

- `pru0_firmware` & `pru1_firmware`: allows to load a custom firmware, like `am335x-pru0-programmer-SWD-fw`

## Virtual Source

- `dac_auxiliary_voltage_raw`: secondary voltage channel of emulator and harvester. Set before starting the experiment if needed.
- `calibration_settings`: Load calibration settings. They are used in the virtual source algorithm.
- `virtual_converter_settings`: Settings which configure the emulator algorithm.
- `virtual_harvester_settings`: Settings for both the emulator and harvester mode

- `sync/error_sum`: Integral of PID control error
- `sync/error`: Instantaneous PID control error
- `sync/correction`: PRU Clock correction (in ticks, ~5ns) as calculated by the PID controller

## PRU Programmer

- `programmer/state`: state machine of the programmer firmware for the PRU, similar to the first state
- `programmer/protocol`: programming protocol (SBW or SWD)
- `programmer/datasize`: after writing the firmware to the shared ram, the actual size has to be written here
- `programmer/datarate`: in bits/second
- `programmer/pin_tck`: gpio pin of the PRU
- `programmer/pin_tdio`: see comment above
- `programmer/pin_tdo`: see comment above
- `programmer/pin_tms`: see comment above

```{note}
PRU0 must be loaded with a special firmware. The sheep-program does that automatically.
```

## References

- [sysfs in kernel module](https://github.com/orgua/shepherd/blob/main/software/kernel-module/src/sysfs_interface.c)
- [sysfs in sheep program](https://github.com/orgua/shepherd/blob/main/software/python-package/shepherd_sheep/sysfs_interface.py)
