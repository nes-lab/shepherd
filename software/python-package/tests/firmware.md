# Firmwares

## Usage

```Bash
	sudo shepherd-sheep -vvv program --mcu-port 1 --mcu-type nrf52  firmware_nrf52_testable.hex
	sudo shepherd-sheep -vvv program --mcu-port 2 --mcu-type msp430 firmware_msp430_testable.hex
	sudo shepherd-sheep target-power
```


## firmware_nrf52_powered.hex

The app monitors up to eight GPIO pins for rising edges and upon detection prints the index of the pin where the edge was detected over UART. Simultaneously, it waits for incoming messages on the UART. When receiving an ASCII encoded number between 0 and the number of configured pins, the app sets the corresponding pin high for ~100us.

Edit the `pins` array and the UART pin definitions at the top of `src/main.c` to reflect your hardware.

### Functionality

- LEDs
	- blink / switch 10x at startup
	- 50 / 150 ms
	- P0_13, _14 (Target v2.1)
- UART
	- P0_06 TX, _08 RX (Target v2.1, SDK)
	- listens and answers
	- should answer when GPIOs are triggered
- GPIO
	- active: P0_20 - P0_25 (GPIO 0 to 5)
	- switch on for 100 us after receiving on UART ("(%u)\r\n")

[Source](https://github.com/orgua/shepherd-targets/tree/main/nrf52_testable)

## firmware_msp52_testable.hex

The firmware toggles all 3 LEDs 16 times for 100 ms and does the same for the 10 external GPIO (4 times).

### Functionality

- LEDs
    - blink / switch on 16x at startup
    - 100 ms on / 100 ms off
- GPIO
    - active: P0_20 - P0_25 (GPIO 0 to 5)
    - switch on for 100 us after receiving on UART ("(%u)\r\n")

[Source](https://github.com/orgua/shepherd-targets/tree/main/msp430_testable)


## Error 1

Samples per buffer:     10000
Number of buffers:      64
Buffer period:          0.100 s
Size of 1 Buffer:       243872 byte
wrote Firmware-Data to SharedMEM-Buffer (size = 4641 bytes)
set programmerCTRL
        target = 'msp430'
        datarate = '500000'
        pin_tck = '8'
        pin_tdio = '9'
        pin_dir_tdio = '11'
        pin_tdo = '0'
        pin_tms = '0'
        pin_dir_tms = '0'
Programmer initialized, will start now
Programming in progress,        pgm_state = init, shp_state = reset
SystemError - Failed during Programming, p_state = error (-2)
Programming - Procedure failed - will exit now!
        shepherdState   = idle
        programmerState = error (-2)
        programmerCtrl  = ['msp430', '500000', '8', '9', '11', '0', '0', '0']
Now exiting ShepherdIO
ShepherdIO is commanded to power down / cleanup
Set voltage of supply for auxiliary Target to 0.000 V (raw=0)
Sending raw auxiliary voltage (dac channel B): 0
Set target-io level converter to disabled
Set Emulator of shepherd-cape to disabled
Set Recorder of shepherd-cape to disabled
Set power-supplies of shepherd-cape to disabled
Shepherd hardware is now powered down
Will set pru0-firmware to 'am335x-pru0-shepherd-fw'

## Error 2

EEPROM provided calibration-settings
Set power-supplies of shepherd-cape to enabled
Set target-io level converter to disabled
Shepherd hardware is powered up
Switching to 'debug'-mode
sysfs/mode: 'debug'
--- Logging error ---
Traceback (most recent call last):
  File "/usr/lib/python3.10/logging/__init__.py", line 1100, in emit
    msg = self.format(record)
  File "/usr/local/lib/python3.10/dist-packages/chromalog/log.py", line 180, in format
    return super(ColorizingStreamHandler, self).format(record)
  File "/usr/lib/python3.10/logging/__init__.py", line 943, in format
    return fmt.format(record)
  File "/usr/local/lib/python3.10/dist-packages/chromalog/log.py", line 79, in format
    with self._patch_record(record, colorizer, message_color_tag):
  File "/usr/lib/python3.10/contextlib.py", line 135, in __enter__
    return next(self.gen)
  File "/usr/local/lib/python3.10/dist-packages/chromalog/log.py", line 55, in _patch_record
    record.getMessage(),
  File "/usr/lib/python3.10/logging/__init__.py", line 368, in getMessage
    msg = msg % self.args
TypeError: %X format: an integer is required, not ColorizedObject
Call stack:
  File "/usr/local/bin/shepherd-sheep", line 8, in <module>
    sys.exit(cli())
  File "/usr/local/lib/python3.10/dist-packages/click/core.py", line 1130, in __call__
    return self.main(*args, **kwargs)
  File "/usr/local/lib/python3.10/dist-packages/click/core.py", line 1055, in main
    rv = self.invoke(ctx)
  File "/usr/local/lib/python3.10/dist-packages/click/core.py", line 1657, in invoke
    return _process_result(sub_ctx.command.invoke(sub_ctx))
  File "/usr/local/lib/python3.10/dist-packages/click/core.py", line 1404, in invoke
    return ctx.invoke(self.callback, **ctx.params)
  File "/usr/local/lib/python3.10/dist-packages/click/core.py", line 760, in invoke
    return __callback(*args, **kwargs)
  File "/usr/local/lib/python3.10/dist-packages/shepherd/cli.py", line 463, in program
    run_programmer(cfg)
  File "/usr/local/lib/python3.10/dist-packages/shepherd/__init__.py", line 80, in run_programmer
    with ShepherdDebug(use_io=False) as sd:
  File "/usr/local/lib/python3.10/dist-packages/shepherd/shepherd_debug.py", line 63, in __enter__
    super().__enter__()
  File "/usr/local/lib/python3.10/dist-packages/shepherd/shepherd_io.py", line 137, in __enter__
    self.refresh_shared_mem()
  File "/usr/local/lib/python3.10/dist-packages/shepherd/shepherd_io.py", line 226, in refresh_shared_mem
    log.debug(
Message: 'Shared memory address: \t0x%08X, size: %d byte'
Arguments: (2627731456, 15607808)
Samples per buffer:     10000
Number of buffers:      64
Buffer period:          0.100 s
Size of 1 Buffer:       243872 byte
Set Recorder of shepherd-cape to enabled
Set Emulator of shepherd-cape to enabled
Set routing for (main) supply with current-monitor to target A
Set Emulator of shepherd-cape to enabled
Set routing for IO to Target A
Set target-io level converter to enabled
Set voltage of supply for auxiliary Target to 3.000 V (raw=39321)
Sending raw auxiliary voltage (dac channel B): 39321
Will set pru0-firmware to 'am335x-pru0-programmer-SWD-fw'
--- Logging error ---
Traceback (most recent call last):
  File "/usr/lib/python3.10/logging/__init__.py", line 1100, in emit
    msg = self.format(record)
  File "/usr/local/lib/python3.10/dist-packages/chromalog/log.py", line 180, in format
    return super(ColorizingStreamHandler, self).format(record)
  File "/usr/lib/python3.10/logging/__init__.py", line 943, in format
    return fmt.format(record)
  File "/usr/local/lib/python3.10/dist-packages/chromalog/log.py", line 79, in format
    with self._patch_record(record, colorizer, message_color_tag):
  File "/usr/lib/python3.10/contextlib.py", line 135, in __enter__
    return next(self.gen)
  File "/usr/local/lib/python3.10/dist-packages/chromalog/log.py", line 55, in _patch_record
    record.getMessage(),
  File "/usr/lib/python3.10/logging/__init__.py", line 368, in getMessage
    msg = msg % self.args
TypeError: %X format: an integer is required, not ColorizedObject
Call stack:
  File "/usr/local/bin/shepherd-sheep", line 8, in <module>
    sys.exit(cli())
  File "/usr/local/lib/python3.10/dist-packages/click/core.py", line 1130, in __call__
    return self.main(*args, **kwargs)
  File "/usr/local/lib/python3.10/dist-packages/click/core.py", line 1055, in main
    rv = self.invoke(ctx)
  File "/usr/local/lib/python3.10/dist-packages/click/core.py", line 1657, in invoke
    return _process_result(sub_ctx.command.invoke(sub_ctx))
  File "/usr/local/lib/python3.10/dist-packages/click/core.py", line 1404, in invoke
    return ctx.invoke(self.callback, **ctx.params)
  File "/usr/local/lib/python3.10/dist-packages/click/core.py", line 760, in invoke
    return __callback(*args, **kwargs)
  File "/usr/local/lib/python3.10/dist-packages/shepherd/cli.py", line 463, in program
    run_programmer(cfg)
  File "/usr/local/lib/python3.10/dist-packages/shepherd/__init__.py", line 91, in run_programmer
    sd.refresh_shared_mem()  # address might have changed
  File "/usr/local/lib/python3.10/dist-packages/shepherd/shepherd_io.py", line 226, in refresh_shared_mem
    log.debug(
Message: 'Shared memory address: \t0x%08X, size: %d byte'
Arguments: (2627731456, 15607808)
Samples per buffer:     10000
Number of buffers:      64
Buffer period:          0.100 s
Size of 1 Buffer:       243872 byte
wrote Firmware-Data to SharedMEM-Buffer (size = 29882 bytes)
set programmerCTRL
        target = 'nrf52'
        datarate = '500000'
        pin_tck = '5'
        pin_tdio = '4'
        pin_dir_tdio = '10'
        pin_tdo = '0'
        pin_tms = '0'
        pin_dir_tms = '0'
Programmer initialized, will start now
Programming in progress,        pgm_state = init, shp_state = idle
SystemError - Failed during Programming, p_state = error (-2)
Programming - Procedure failed - will exit now!
        shepherdState   = idle
        programmerState = error (-2)
        programmerCtrl  = ['nrf52', '500000', '5', '4', '10', '0', '0', '0']
Now exiting ShepherdIO
ShepherdIO is commanded to power down / cleanup
Set voltage of supply for auxiliary Target to 0.000 V (raw=0)
Sending raw auxiliary voltage (dac channel B): 0
Set target-io level converter to disabled
Set Emulator of shepherd-cape to disabled
Set Recorder of shepherd-cape to disabled
Set power-supplies of shepherd-cape to disabled
Shepherd hardware is now powered down
Will set pru0-firmware to 'am335x-pru0-shepherd-fw'
